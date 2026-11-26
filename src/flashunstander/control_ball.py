"""A small desktop launcher with a circular native hit region."""

from math import atan2, ceil, cos, degrees, exp, floor, hypot, sin, tau
from os import environ
from random import Random
from time import monotonic

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, QPointF, QSettings
from PySide6.QtGui import QCursor, QRegion, QPainter, QColor, QRadialGradient, QPen, QPolygonF, QLinearGradient, QVector4D
from .starfield import Starfield
from .texture_cache import DetailTextureCache
from .gpu_spheres import GpuSphereLayer
from .closeup import CloseupCamera, flight_progress
from .cosmic import RING_EXTENT, ring_for_conversation, sphere
from .earth_material import earth_storm_motion, earth_storm_origin, earth_weather_phases
from .ring_material import ring_profile_for_conversation
from .orbit import (
    PLANET_MATERIALS, guide_points, orbit_for, orbital_speed, planet_mass_ratio,
    planet_radius, project, physical_orbit_axis, physical_planet_radius,
    AU_IN_EARTH_RADII, PHYSICAL_STAR_RADIUS,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMenu, QMessageBox, QPushButton, QSlider,
)


STANDBY_STAR_RADIUS = 58
STANDBY_PLANET_SCALE = 1.08
AURORA_HEIGHT_SCALE = 5.
AURORA_FOOT_HEIGHT = .045
AURORA_MAX_HEIGHT = AURORA_FOOT_HEIGHT + AURORA_HEIGHT_SCALE * (.405 - AURORA_FOOT_HEIGHT)
EXPANDED_STAR_RADIUS = 19
FRAME_INTERVAL = 1 / 60


ORBIT_COLORS = (
    ("highlightColor", "选中颜色（RGB）", "#ffc24f"),
    ("orbitColor", "未选中轨道颜色（RGB）", "#a6bcd3"),
)


APPEARANCE_CONTROLS = (
    ("standbySize", "待机尺寸", 65, 145, 100),
    ("expandedSize", "选中模式尺寸", 65, 145, 100),
    ("brightness", "星系整体亮度", 55, 145, 95),
    ("shadowLight", "行星阴影补光", 12, 60, 36),
    ("starfieldOpacity", "星空背景不透明度", 0, 100, 50),
    ("highlightWidth", "选中轨道与框线宽", 8, 45, 22),
    ("orbitWidth", "未选中轨道线宽", 4, 35, 8),
)


class ControlBall(QPushButton):
    def __init__(self, app, controls, *, shortcut_available=True):
        super().__init__("F")
        self.controls = controls
        self._appearance_settings = QSettings("flashUnstander", "Appearance")
        self._appearance = {
            key: max(low, min(high, self._appearance_settings.value(key, default, type=int)))
            for key, _, low, high, default in APPEARANCE_CONTROLS
        }
        self._orbit_colors = {}
        for key, _, default in ORBIT_COLORS:
            color = QColor(self._appearance_settings.value(key, default))
            self._orbit_colors[key] = color if color.isValid() else QColor(default)
        self.shortcut_available = shortcut_available
        self._press_position = None
        self._dragging = False
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("新建 flashUnstander 问答窗口")
        self.setWindowTitle("flashUnstander 中控")
        self.clicked.connect(controls.openNew)
        controls.windowsChanged.connect(self._refresh_tooltip)
        self._refresh_tooltip()
        self.setFixedSize(270, 270)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        self.expansion = 0.
        self._velocity = 0.
        self._orbital_angles = []
        self._spin_time = 0.
        self.focused = -1
        self._flight_target = -1
        self._flight_started = 0.
        self._flight_origin = {-1: 1.}
        self._flight_weights = {-1: 1.}
        self._saved_focus = self._appearance_settings.value("focusConversation", "", type=str)
        self.targets = []
        self._appearance_preview = None
        self._hover_anchor = None
        self._hover_until = 0.0
        self._hover_rearm_at = None
        self.timer = QTimer(self, singleShot=True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._frame_tick)
        area = app.primaryScreen().availableGeometry()
        self._anchor = area.bottomRight() - QPoint(147, 147)
        self._texture_cache = DetailTextureCache()
        deleted = getattr(controls, "conversationDeleted", None)
        if deleted is not None:
            deleted.connect(self._texture_cache.delete)
        self._gpu_layer = None
        if environ.get("FLASHUNSTANDER_GPU", "1") == "1":
            layer = GpuSphereLayer(self._texture_cache)
            if layer.supported():
                self._gpu_layer = layer
                app.aboutToQuit.connect(layer.close)
                layer.sceneGraphError.connect(self._disable_gpu_layer)
            else:
                layer.deleteLater()
        self._starfield = Starfield(self._appearance["starfieldOpacity"] / 50)
        app.aboutToQuit.connect(self._starfield.close)
        self._viewport_key = None
        self._orbit_paths = {}
        self._sync_viewport()
        self._preload_plan = ()
        self._preload_direction = 1
        self._preload_timer = QTimer(self, interval=140, singleShot=True)
        self._preload_timer.timeout.connect(self._preload_detail)
        self._last_tick = monotonic()
        self._next_frame = self._last_tick + FRAME_INTERVAL
        self._schedule_frame(self._last_tick)

    def _schedule_frame(self, now):
        self.timer.start(max(1, ceil((self._next_frame - now)*1000)))

    def _frame_tick(self):
        self._advance(monotonic())
        after_render_request = monotonic()
        # Keep a fractional 16.67 ms cadence. Skip missed deadlines without
        # replaying old frames or discarding elapsed simulation time.
        periods = max(1, floor((after_render_request - self._next_frame)/FRAME_INTERVAL) + 1)
        self._next_frame += periods * FRAME_INTERVAL
        self._schedule_frame(after_render_request)

    def _advance(self, now=None):
        now = monotonic() if now is None else now
        dt = max(0., now - self._last_tick)
        self._last_tick = now
        target = (float(self._hover_active(now)) if self._appearance_preview is None
                  else self._appearance_preview)
        # Closed-form critically damped spring. Retain velocity on reversal.
        offset = self.expansion - target
        frequency = 10.
        impulse = self._velocity + frequency*offset
        decay = exp(-frequency*dt)
        self.expansion = target + (offset + impulse*dt)*decay
        self._velocity = (self._velocity - frequency*impulse*dt)*decay
        if not 0 < self.expansion < 1 or (
            abs(self.expansion - target) < .001 and abs(self._velocity) < .01
        ):
            self.expansion = target
            self._velocity = 0.
        if self._saved_focus:
            for index in range(self.controls.windowCount):
                if self.controls.conversationId(index) == self._saved_focus:
                    self.focused = index
                    self._saved_focus = ""
                    break
        self._sync_viewport()
        self._schedule_detail_preload()
        self._update_flight(now)
        masses, _, axes, _ = self._planet_layout(self.expansion * self._flight_weights.get(-1, 0.))
        for i, axis in enumerate(axes):
            if i == len(self._orbital_angles):
                self._orbital_angles.append((.22 + i*2.39996) % tau)
            self._orbital_angles[i] = (
                self._orbital_angles[i] + dt*orbital_speed(axis, masses[i])
            ) % tau
        self._spin_time += dt
        if self._starfield.isVisible():
            self._starfield.update()
        self.update()

    def retain_planet_textures(self, conversation_ids):
        self._texture_cache.retain([*conversation_ids, "solar-core"])

    def _texture_key(self, index):
        if index < 0:
            return "0/0/detail/solar-core"
        kind = 1 + index % 4
        identifier = self.controls.conversationId(index)
        return f"{kind}/{index+1}/detail/{identifier}" if identifier else ""

    def _schedule_detail_preload(self, *, immediate=False):
        if self._gpu_layer is None or not self.isVisible():
            return
        count = self.controls.windowCount
        if count:
            target = self.focused if 0 <= self.focused < count else (
                0 if self._preload_direction > 0 else count - 1
            )
            neighbors = (target, (target + self._preload_direction) % count,
                         (target - self._preload_direction) % count)
            visible = (range(count) if self.expansion < .4 or self.focused < 0
                       else (i for _, _, i in self.targets if 0 <= i < count))
            order = (neighbors[0], -1, *neighbors[1:], *visible)
        else:
            order = (-1,)
        plan = tuple(key for index in dict.fromkeys(order) if (key := self._texture_key(index)))
        if immediate:
            self._preload_plan = plan
            self._preload_timer.stop()
            self._preload_detail()
        elif plan != self._preload_plan:
            self._preload_plan = plan
            self._preload_timer.start()

    def _preload_detail(self):
        if self._gpu_layer is not None and self.isVisible():
            self._gpu_layer.preload_detail(*self._preload_plan)
        else:
            self._preload_plan = ()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_starfield()
        self._sync_gpu_layer()

    def hideEvent(self, event):
        self._starfield.hide()
        if self._gpu_layer is not None:
            self._gpu_layer.hide()
        super().hideEvent(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_starfield"):
            self._starfield.move(self.pos())
            self._sync_gpu_layer()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_starfield"):
            self._starfield.resize(self.size())
            self._sync_gpu_layer()

    def _disable_gpu_layer(self):
        layer = self._gpu_layer
        if layer is not None:
            self._gpu_layer = None
            layer.hide()
            layer.deleteLater()
            self.update()

    def _sync_gpu_layer(self):
        layer = self._gpu_layer
        if layer is None:
            return
        layer.setGeometry(self.geometry())
        if self.isVisible() and not layer.isVisible():
            layer.show()
            layer.raise_()
            self.raise_()

    def _sync_starfield(self):
        self._starfield.setGeometry(self.geometry())
        if self._starfield.opacity > 0 and self.isVisible():
            if not self._starfield.isVisible():
                self._starfield.show()
                if self._gpu_layer is not None:
                    self._gpu_layer.raise_()
                self.raise_()
            self._starfield.update()
        else:
            self._starfield.hide()

    def _body_at(self, point):
        for center, radius, index in reversed(self.targets):
            if hypot(point.x() - center.x(), point.y() - center.y()) <= radius + 1:
                return index
        return None

    def _hover_active(self, now):
        cursor = QCursor.pos()
        if self._hover_rearm_at is not None:
            # During collapse, changing geometry must not re-arm a still cursor.
            delta = cursor - self._hover_rearm_at
            if self.expansion > 0 or delta.manhattanLength() < 4:
                return False
            self._hover_rearm_at = None
        point = self.mapFromGlobal(cursor)
        body = self._body_at(point) if self.rect().contains(point) else None
        over_body = body == -1 if self._hover_anchor is None else body is not None
        if over_body:
            if self._hover_anchor is None:
                self._schedule_detail_preload(immediate=True)
            self._hover_anchor = cursor
        if self._hover_anchor is None:
            return False
        delta = cursor - self._hover_anchor
        if hypot(delta.x(), delta.y()) <= 54:
            self._hover_until = now + .55
            return True
        if now < self._hover_until:
            return True
        self._hover_anchor = None
        self._hover_rearm_at = cursor
        return False

    def _update_flight(self, now):
        if self.expansion == 0.:
            self._flight_target = self.focused
            self._flight_weights = {self.focused: 1.}
            self._flight_origin = self._flight_weights
            self._flight_started = now
            return
        if self.focused != self._flight_target:
            self._flight_origin = self._flight_weights.copy()
            self._flight_target = self.focused
            self._flight_started = now
        progress = min(1., max(0., (now - self._flight_started) / .55))
        if progress == 1.:
            self._flight_weights = {self._flight_target: 1.}
            return
        amount = flight_progress(progress)
        self._flight_weights = {i: weight * (1 - amount)
                                for i, weight in self._flight_origin.items()}
        self._flight_weights[self._flight_target] = self._flight_weights.get(self._flight_target, 0.) + amount

    def _star_radius(self, expansion=None):
        expansion = self.expansion if expansion is None else expansion
        standby = STANDBY_STAR_RADIUS * self._appearance["standbySize"] / 100
        expanded = EXPANDED_STAR_RADIUS * self._appearance["expandedSize"] / 100
        return standby + expansion * (expanded - standby)

    def _size_scale(self, expansion):
        return ((1 - expansion) * self._appearance["standbySize"]
                + expansion * self._appearance["expandedSize"]) / 100

    def _planet_layout(self, expansion=None):
        expansion = self.expansion if expansion is None else expansion
        count = self.controls.windowCount
        masses, sizes = [], []
        scale = self._size_scale(expansion)
        for i in range(count):
            material = PLANET_MATERIALS[i % len(PLANET_MATERIALS)]
            tokens = self.controls.contextTokens(i)
            masses.append(planet_mass_ratio(planet_radius(tokens, 0, material), material))
            diameter_scale = 1 + (STANDBY_PLANET_SCALE - 1) * (1 - expansion)
            sizes.append(planet_radius(tokens, expansion, material) * diameter_scale * scale)
        axes = []
        outer = self._star_radius(expansion)
        for i, size in enumerate(sizes):
            extent = size * self._ring_extent(i)
            eccentricity = orbit_for(i).eccentricity
            axis = (outer + extent + 7) / (1 - eccentricity)
            axes.append(axis)
            outer = axis * (1 + eccentricity) + extent
        return masses, sizes, axes, outer

    def _ring(self, index):
        return ring_for_conversation(self.controls.conversationId(index))

    def _ring_extent(self, index):
        if self._gpu_layer is None:
            return RING_EXTENT if self._ring(index) else 1.
        profile = ring_profile_for_conversation(self.controls.conversationId(index))
        return profile.extent if profile else 1.

    def _sync_viewport(self):
        key = tuple((self.controls.contextTokens(i), self._ring_extent(i))
                    for i in range(self.controls.windowCount))
        if key == self._viewport_key or self._dragging:
            return
        if self._viewport_key is not None and len(key) != len(self._viewport_key):
            self._orbit_paths.clear()
        self._viewport_key = key
        outer = 0.
        for expansion in (0., 1.):
            _, sizes, axes, edge = self._planet_layout(expansion)
            outer = max(outer, edge)
            for i, (size, axis) in enumerate(zip(sizes, axes)):
                aphelion = axis * (1 + orbit_for(i).eccentricity)
                outer = max(outer, aphelion + size * (1 + AURORA_MAX_HEIGHT))
        self._camera = max(620., 4*outer)
        self._resize_scene(outer)

    def _resize_scene(self, outer):
        # A stable anchor keeps growing orbits near the place the user dragged to.
        edge = outer * self._camera / (self._camera - outer) + 12
        subject_extent = self._star_radius(0) * (1 + AURORA_MAX_HEIGHT) + 12 if self.controls.windowCount else 0
        half_size = 8 * ceil(max(135, edge, subject_extent, self._star_radius(0)*2.45) / 8)
        size = 2 * half_size
        if size == self.width() or self._dragging:
            return
        area = self.screen().availableGeometry()
        x = min(max(self._anchor.x() - half_size, area.left()), area.right() + 1 - size)
        y = min(max(self._anchor.y() - half_size, area.top()), area.bottom() + 1 - size)
        # For oversized scenes keep the star inside the work area.
        if size > area.width():
            x = area.center().x() - half_size
        if size > area.height():
            y = area.center().y() - half_size
        self.setFixedSize(size, size)
        self.move(x, y)
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))

    def _orbit_path(self, index, axis, camera):
        key = (axis, camera)
        previous = self._orbit_paths.get(index)
        if previous is not None and previous[0] == key:
            return previous[1]
        points = []
        for ux, uy, uz in guide_points(index):
            x, y, _ = project(axis*ux, axis*uy, axis*uz, camera)
            points.append(QPointF(x, y))
        self._orbit_paths[index] = (key, points)
        return points

    def _orbit_pen(self, index):
        if index == self.focused:
            return self._selection_pen()
        color = QColor(self._orbit_colors["orbitColor"])
        intensity = self._appearance["brightness"] / 100
        color.setAlpha(round((14 + 34*self.expansion) * intensity))
        return QPen(color, self._appearance["orbitWidth"] / 10)

    def _selection_pen(self):
        color = QColor(self._orbit_colors["highlightColor"])
        color.setAlpha(round(14 + 216*self.expansion))
        width = .75 + (self._appearance["highlightWidth"]/10 - .75)*self.expansion
        return QPen(color, width)

    @staticmethod
    def _focus_occludes_target(index, depth, position, radius, target):
        subject, subject_depth, subject_position, subject_radius = target
        if index <= subject or depth <= subject_depth:
            return False
        offset = position - subject_position
        return hypot(offset.x(), offset.y()) < radius + subject_radius

    def _closeup_bodies(self, bodies, positions, focus_radius, weights):
        strength = sum(weights.values())
        if not strength:
            self._starfield.set_view(0., 0., 0., 0.)
            return bodies

        aim = tuple(sum(positions[i][0][axis] * weight for i, weight in weights.items()) / strength
                    for axis in range(3))
        aim_radius = sum(positions[i][1] * weight for i, weight in weights.items()) / strength
        subject = self.focused if self.focused >= 0 else max(weights, key=weights.get)
        subject_position, subject_radius = positions[subject]
        extent = self._ring_extent(subject)
        initial_screen_radius = sum(radius * weights.get(index, 0.)
                                    for _, index, _, _, radius, _, _ in bodies) / strength
        camera = CloseupCamera(aim, aim_radius, focus_radius, strength,
                               min(self.width(), self.height()) * .37,
                               subject_position, subject_radius * extent, initial_screen_radius)
        cx, cy, cz = camera.position
        self._starfield.set_view(strength, cx/AU_IN_EARTH_RADII, cy/AU_IN_EARTH_RADII,
                                cz/AU_IN_EARTH_RADII)

        result = []
        limit = min(self.width(), self.height()) * .68
        for depth, index, x, y, radius, light, opacity in bodies:
            position, physical_radius = positions[index]
            projection = camera.project(position, physical_radius)
            amount = strength
            if projection is None:
                # Other bodies can leave the view through the near clipping plane.
                if index != subject:
                    if strength < .995:
                        result.append((depth, index, x, y, radius, light, 1 - strength))
                    continue
                result.append((depth, index, x, y, radius, light, opacity))
                continue

            pd, px, py, pr, vector = projection
            distance = hypot(px, py)
            if index != subject and distance > limit:
                px, py = px*limit/distance, py*limit/distance
                visibility = max(0., min(1., (2*limit-distance)/limit))
            else:
                visibility = 1.
            opacity = 1 - amount*(1 - visibility)
            if opacity <= .005:
                continue
            if index == -1:
                pr = max(1., pr)
            lx, ly, lz = (old + (new-old)*amount for old, new in zip(light, vector))
            light_norm = max(.001, hypot(lx, ly, lz))
            result.append((depth + (pd-depth)*amount, index,
                           x + (px-x)*amount, y + (py-y)*amount, radius + (pr-radius)*amount,
                           (lx/light_norm, ly/light_norm, lz/light_norm), opacity))
        return result

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        center = QPointF(self.width()/2, self.height()/2)
        p.translate(center)
        e = self.expansion
        focus_radius = self._star_radius(0)
        overview = e * self._flight_weights.get(-1, 0.)
        star_radius = self._star_radius(overview)
        _, radii, axes, _ = self._planet_layout(overview)
        count = len(axes)
        camera = self._camera
        brightness = self._appearance["brightness"] / 100
        shadow_light = self._appearance["shadowLight"] / 100
        gpu_layer = self._gpu_layer if self.isVisible() else None
        approach = flight_progress(e)
        weights = {i: approach*weight for i, weight in self._flight_weights.items()
                   if 0 <= i < count and approach*weight > .001}
        flight_weight = sum(weights.values())
        bodies = [(0., -1, 0., 0., star_radius, (0., 0., 1.), 1.)]
        physical_positions = {-1: ((0., 0., 0.), PHYSICAL_STAR_RADIUS)}
        selection_orbit = None
        for i in range(count):
            orbit = orbit_for(i)
            axis = axes[i]
            mean = self._orbital_angles[i] if i < len(self._orbital_angles) else .22 + i*2.39996
            anomaly = orbit.anomaly(mean)
            x, y, z = orbit.position(anomaly, axis)
            sx, sy, scale = project(x, y, z, camera)
            distance = hypot(x, y, z)
            light = (-x/distance, -y/distance, -z/distance)
            radius = radii[i] * scale
            if weights:
                physical_positions[i] = (
                    orbit.position(anomaly, physical_orbit_axis(i)),
                    physical_planet_radius(i, self.controls.contextTokens(i)),
                )
            if i == self.focused:
                selection_orbit = orbit, anomaly, axis
            bodies.append((z, i, sx, sy, radius, light, 1.))

        bodies = self._closeup_bodies(bodies, physical_positions, focus_radius, weights)
        protected_target = None
        if weights.get(self.focused, 0.) > .85:
            for depth, i, x, y, radius, _, _ in bodies:
                if i == self.focused:
                    extent = self._ring_extent(i)
                    protected_target = (i, depth, center + QPointF(x, y), radius * extent)
                    break

        p.save()
        sun = next((body for body in bodies if body[1] == -1), None)
        if gpu_layer is None and sun is not None:
            _, _, sun_x, sun_y, sun_radius, _, sun_opacity = sun
            sun_position = QPointF(sun_x, sun_y)
            halo = sun_radius * 2.45
            glow = QRadialGradient(sun_position, halo)
            for stop, color in (
                (0, QColor(255, 202, 125, 210)), (.40, QColor(255, 182, 83, 140)),
                (.46, QColor(255, 149, 62, 75)), (.64, QColor(233, 111, 44, 26)),
                (1, QColor(217, 91, 34, 0)),
            ):
                color.setAlpha(min(255, round(color.alpha() * brightness * sun_opacity)))
                glow.setColorAt(stop, color)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(sun_position, halo, halo)

        gpu_orbits = []
        for i, axis in enumerate(axes):
            pen = self._orbit_pen(i)
            color = pen.color()
            color.setAlpha(round(color.alpha() * (1 - flight_weight)))
            pen.setColor(color)
            if color.alpha() == 0:
                continue
            points = self._orbit_path(i, axis, camera)
            if gpu_layer is None:
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolyline(QPolygonF(points))
            else:
                gpu_orbits.append(dict(
                    points=[center + point for point in points],
                    color=pen.color(), lineWidth=pen.widthF(),
                ))

        gpu_frame = ([dict(texture=self._texture_key(i), terrestrial=float(i >= 0 and i % 4 == 0))
                      for i in range(-1, count)] if gpu_layer is not None else [])
        weather_drift, cirrus_drift, weather_evolution = earth_weather_phases(self._spin_time)
        self.targets.clear()
        for draw_order, (depth, i, x, y, radius, light, opacity) in enumerate(sorted(bodies)):
            position = center + QPointF(x, y)
            screen_radius = radius
            ring = self._ring(i) if i >= 0 else None
            if i >= 0 and i != self.focused and protected_target is not None and self._focus_occludes_target(
                i, depth, position, screen_radius * self._ring_extent(i), protected_target,
            ):
                continue
            if i != self.focused:
                # Leave room for the planet's halo, rings or aurora off screen.
                margin = screen_radius * 3
                if not QRectF(-margin, -margin, self.width()+2*margin,
                              self.height()+2*margin).contains(position):
                    continue
            kind = 0 if i < 0 else 1 + i % 4
            spin = self._spin_time * (.055 if i < 0 else .16 + .022*(i % 4)) + kind
            p.setOpacity(opacity)
            if gpu_layer is None:
                image, extent = sphere(kind, radius, self.devicePixelRatioF(), light, spin, i + 1,
                                       brightness=brightness, shadow_light=shadow_light, ring=ring)
                p.drawImage(QRectF(x-extent, y-extent, 2*extent, 2*extent), image)
            else:
                profile = ring_profile_for_conversation(self.controls.conversationId(i)) if ring else None
                factor = 2.45 if i < 0 else profile.extent if profile else 1.05 if kind == 1 else 1.
                extent = radius * factor
                lx, ly, lz = light
                red, green, blue = ring[1] if ring else (0, 0, 0)
                ring_parameters = {}
                if profile:
                    ring_parameters = dict(
                        ringPattern=QVector4D(profile.inner, profile.outer, profile.bands, profile.gaps),
                        ringSeed=float(profile.seed), ringReflectivity=profile.reflectivity,
                        ringPhase=(self._spin_time * .22) % tau,
                    )
                detail = i >= 0 and i == self.focused and flight_weight > .04
                storms = {}
                if kind == 1:
                    storms = {
                        f"storm{index}": QVector4D(*state)
                        for index, state in enumerate(earth_storm_motion(self._spin_time, i + 1))
                    }
                gpu_frame[i + 1] = dict(
                    px=position.x()-extent, py=position.y()-extent, diameter=2*extent, alpha=opacity,
                    depth=draw_order + 1, extent=factor, spin=spin % tau,
                    tilt=(.13, -.21, .31, -.28, .20)[kind], axialTip=-.328 if kind == 3 else .12,
                    selfLit=float(i < 0), lx=lx, ly=ly, lz=lz,
                    brightness=brightness, shadowLight=shadow_light,
                    rr=red/255, rg=green/255, rb=blue/255,
                    texture=gpu_frame[i + 1]["texture"], kind=kind,
                    weatherDrift=weather_drift, cirrusDrift=cirrus_drift,
                    weatherEvolution=weather_evolution,
                    stormOrigin=earth_storm_origin(i + 1) if kind else 0.,
                    terrestrial=float(kind == 1), detailLevel=float(detail), **storms, **ring_parameters,
                )
                # A nearly transparent disc keeps native click and drag targets.
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 1))
                p.drawEllipse(QPointF(x, y), radius, radius)
            aurora_opacity = self.controls.planetAuroraOpacity(i) if i >= 0 else 0.
            if aurora_opacity > 0:
                self._draw_aurora(p, x, y, radius, self.controls.conversationId(i), aurora_opacity)
            self.targets.append((position, screen_radius, i))
            if i == self.focused and e > .5:
                pen = self._selection_pen()
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                frame_radius = (radius if i < 0 else extent) + 4
                bounds = QRectF(x-frame_radius, y-frame_radius, 2*frame_radius, 2*frame_radius)
                angles = (0, 90, 180, 270)
                if selection_orbit is not None and flight_weight < .15:
                    orbit, anomaly, axis = selection_orbit
                    joins = []
                    # Put two arcs at the crossings of the orbit and frame.
                    for direction in (-1, 1):
                        low, high = 0., 1.57
                        for _ in range(14):
                            step = (low + high) / 2
                            px, py, _ = project(*orbit.position(anomaly + direction*step, axis), camera)
                            if hypot(px - x, py - y) < frame_radius:
                                low = step
                            else:
                                high = step
                        joins.append(degrees(atan2(y - py, px - x)))
                    turn = (joins[1] - joins[0]) % 360
                    angles = (*joins, joins[0] + turn/2, joins[1] + (360-turn)/2)
                for angle in angles:
                    p.drawArc(bounds, round(angle*16)-350, 700)
        p.restore()
        if e > .40:
            label = f"会话 {self.focused + 1} / {count}" if self.focused >= 0 else "恒星 · 点击新建会话"
            width = p.fontMetrics().horizontalAdvance(label) + 22
            bounds = QRectF(-width/2, 83, width, 24)
            p.setOpacity((e-.40)/.60)
            p.setPen(QPen(QColor(204, 177, 138, 60), .8))
            p.setBrush(QColor(19, 22, 29, 213))
            p.drawRoundedRect(bounds, 12, 12)
            p.setPen(QColor("#f3d9b2"))
            p.drawText(bounds, Qt.AlignmentFlag.AlignCenter, label)
        p.end()
        if gpu_layer is not None:
            gpu_layer.submit(gpu_frame, gpu_orbits)

    def _draw_aurora(self, painter, x, y, radius, conversation_id, opacity):
        rng = Random(conversation_id or "aurora")
        base_color, upper_color = rng.choice((
            ("#43ee86", "#8dffbe"), ("#39e99c", "#ed496b"),
            ("#56ff97", "#9f73ff"), ("#538cff", "#df74fb"),
            ("#ee446c", "#ff8eab"),
        ))
        clock = self._spin_time
        segments = 64
        # Magnetic pole leans toward the viewer. Each point is in planet radii.
        tilt = .51
        pole_y, pole_z = -cos(tilt), sin(tilt)
        points = []
        for i in range(segments + 1):
            angle = tau*i/segments
            oval = .48 + .045*sin(3*angle + .5*clock) + .025*sin(7*angle - clock)
            curtain = .19 + .14*(.5 + .5*sin(5*angle - 1.2*clock))**2
            curtain += .075*(.5 + .5*sin(11*angle + 1.7*clock))
            curtain = AURORA_FOOT_HEIGHT + AURORA_HEIGHT_SCALE * (curtain - AURORA_FOOT_HEIGHT)
            brightness = .68 + .32*(.5 + .5*sin(4*angle - clock))**2
            layers = []
            for height in (.015, AURORA_FOOT_HEIGHT, curtain):
                distance = 1 + height
                pole = cos(oval) * distance
                band = sin(oval) * distance
                px = band*cos(angle)
                across = band*sin(angle)
                py = pole*pole_y + across*pole_z
                pz = pole*pole_z - across*pole_y
                layers.append((px, py, pz))
            points.append((layers, brightness))

        painter.save()
        painter.translate(x, y)
        painter.rotate(-18)
        painter.setOpacity(opacity)
        painter.setPen(Qt.PenStyle.NoPen)
        for segment, (left, right) in enumerate(zip(points, points[1:])):
            l, intensity = left
            r, _ = right
            for bottom, top in ((0, 1), (1, 2)):
                quad = (l[bottom], r[bottom], r[top], l[top])
                # Fade partially occulted segments at the limb.
                cover = sum(pz >= 0 or px*px + py*py >= 1 for px, py, pz in quad) / 4
                if not cover:
                    continue
                vertices = [QPointF(radius*px, radius*py) for px, py, _ in quad]
                gradient = QLinearGradient((vertices[0]+vertices[1])/2,
                                           (vertices[2]+vertices[3])/2)
                foot = QColor(base_color)
                crest = QColor(upper_color if top == 2 else base_color)
                flicker = .88 + .12*sin(clock*2.7 + segment*.43)
                foot.setAlpha(round((218 if top == 1 else 226)*cover*intensity*flicker))
                crest.setAlpha(round(236*cover*intensity*flicker) if top == 1 else 0)
                gradient.setColorAt(0, foot)
                gradient.setColorAt(1, crest)
                if top == 2:
                    upper = QColor(upper_color)
                    upper.setAlpha(round(125*cover*intensity*flicker))
                    gradient.setColorAt(.48, upper)
                painter.setBrush(gradient)
                painter.drawPolygon(QPolygonF(vertices))
        painter.restore()

    def wheelEvent(self, event):
        count = self.controls.windowCount
        wheel = event.angleDelta().y()
        if count and wheel and (self._hover_anchor is not None or self._appearance_preview == 1.):
            step = 1 if wheel < 0 else -1
            self.focused = (self.focused + 1 + step) % (count + 1) - 1
            self._preload_direction = step
            self._saved_focus = ""
            identifier = self.controls.conversationId(self.focused) if self.focused >= 0 else ""
            self._appearance_settings.setValue("focusConversation", identifier or "")
            self._schedule_detail_preload(immediate=True)
            self.update()
            event.accept()
            return
        event.ignore()

    def _refresh_tooltip(self):
        shortcut = "Alt+Shift+W 新建窗口" if self.shortcut_available else "Alt+Shift+W 注册失败"
        self.setToolTip(
            f"flashUnstander · 已显示 {self.controls.visibleCount}/{self.controls.windowCount} 个窗口\n{shortcut}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.globalPosition().toPoint()
            self._start_position = self.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_position is None or not event.buttons() & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)
            return
        pointer = event.globalPosition().toPoint()
        delta = pointer - self._press_position
        if self._dragging or delta.manhattanLength() >= QApplication.startDragDistance():
            self.setDown(False)
            self._dragging = True
            self.move(self._start_position + delta)
            self._anchor = self.geometry().center()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = None
            if self._dragging:
                self._dragging = False
                event.accept()
                return
            index = self._body_at(event.position())
            if index is not None:
                self.setDown(False)
                if index < 0:
                    self.controls.openNew()
                else:
                    self.controls.openWindow(index)
                event.accept()
                return
            self.setDown(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        index = self._body_at(event.pos())
        if index is not None and index >= 0:
            action = menu.addAction("删除会话…")
            action.setEnabled(self.controls.canDeleteWindow(index))
            if menu.exec(event.globalPos()) is action:
                self._confirm_delete(index)
            return
        menu.addAction("打开最近窗口", self.controls.openRecent)
        menu.addAction("新建问答窗", self.controls.openNew)
        menu.addAction("显示全部窗口", self.controls.showAll).setEnabled(self.controls.windowCount > 0)
        menu.addAction("星系外观设置…", self._open_appearance)
        menu.addAction("设置", self.controls.openSettings)
        menu.addSeparator()
        menu.addAction("退出", self.controls.quit)
        menu.exec(event.globalPos())

    def _open_appearance(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("星系外观设置")
        dialog.setMinimumWidth(360)
        layout = QFormLayout(dialog)
        sliders = []
        for key, title, low, high, default in APPEARANCE_CONTROLS:
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(low, high)
            slider.setValue(self._appearance[key])
            value = QLabel(self._appearance_value(key, slider.value()))
            value.setMinimumWidth(38)
            row = QHBoxLayout()
            row.addWidget(slider)
            row.addWidget(value)
            layout.addRow(title, row)
            slider.valueChanged.connect(
                lambda number, name=key, label=value: self._set_appearance(name, label, number)
            )
            sliders.append((slider, default))
        color_buttons = []
        for key, title, default in ORBIT_COLORS:
            button = QPushButton()
            self._show_color(key, button)
            button.clicked.connect(
                lambda checked=False, name=key, control=button: self._pick_orbit_color(dialog, name, control)
            )
            layout.addRow(title, button)
            color_buttons.append((key, button, default))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close
                                   | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.rejected.connect(dialog.reject)
        def restore_defaults():
            for slider, default in sliders:
                slider.setValue(default)
            for key, button, default in color_buttons:
                self._apply_orbit_color(key, QColor(default), button, save=True)
            self._appearance_preview = 1.

        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(restore_defaults)
        layout.addRow(buttons)
        dialog.adjustSize()
        area = self.screen().availableGeometry()
        dialog.move(area.left() + 24, area.top() + 24)
        self._appearance_preview = 1.
        dialog.exec()
        self._appearance_preview = None
        dialog.deleteLater()

    def _set_appearance(self, key, label, value):
        self._appearance[key] = value
        self._appearance_settings.setValue(key, value)
        label.setText(self._appearance_value(key, value))
        if key == "starfieldOpacity":
            self._starfield.opacity = value / 50
            self._sync_starfield()
        if key in ("standbySize", "expandedSize"):
            self._appearance_preview = float(key == "expandedSize")
            self._viewport_key = None
            self._sync_viewport()
        self.update()

    @staticmethod
    def _appearance_value(key, value):
        return f"{value/10:.1f} px" if key.endswith("Width") else f"{value}%"

    def _show_color(self, key, button):
        color = self._orbit_colors[key]
        hex_color = color.name().upper()
        button.setText(hex_color)
        text = "#141414" if color.lightness() > 135 else "#ffffff"
        button.setStyleSheet(f"background-color: {hex_color}; color: {text}")

    def _apply_orbit_color(self, key, color, button, *, save=False):
        self._orbit_colors[key] = QColor(color)
        if save:
            self._appearance_settings.setValue(key, color.name())
        self._show_color(key, button)
        self.update()

    def _pick_orbit_color(self, parent, key, button):
        original = QColor(self._orbit_colors[key])
        picker = QColorDialog(original, parent)
        picker.setWindowTitle("轨道颜色")
        picker.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog)
        picker.currentColorChanged.connect(lambda color: self._apply_orbit_color(key, color, button))
        if picker.exec() == QDialog.DialogCode.Accepted:
            self._apply_orbit_color(key, picker.selectedColor(), button, save=True)
        else:
            self._apply_orbit_color(key, original, button)

    def _confirm_delete(self, index):
        buttons = QMessageBox.StandardButton
        choice = QMessageBox.question(
            self, "删除会话", "永久删除这颗行星及其聊天记录？",
            buttons.Yes | buttons.Cancel, buttons.Cancel,
        )
        if choice != buttons.Yes:
            return
        try:
            deleted = self.controls.deleteWindow(index)
        except Exception as error:
            QMessageBox.warning(self, "删除失败", str(error))
            return
        if deleted:
            if index < len(self._orbital_angles):
                self._orbital_angles.pop(index)
            self.targets.clear()
            if index < self.focused:
                self.focused -= 1
            elif index == self.focused:
                self.focused = -1
                self._appearance_settings.remove("focusConversation")
            self.update()
        else:
            QMessageBox.warning(self, "暂时无法删除", "请等待当前回复结束，或先停止生成。")
