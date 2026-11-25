"""A small desktop launcher with a circular native hit region."""

from math import atan2, ceil, degrees, exp, hypot, tau
from time import monotonic

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, QPointF, QSettings
from PySide6.QtGui import QCursor, QRegion, QPainter, QColor, QRadialGradient, QPen, QPolygonF
from .cosmic import RING_EXTENT, ring_state, sphere
from .orbit import (
    PLANET_MATERIALS, guide_points, orbit_for, orbital_speed, planet_mass_ratio,
    planet_radius, project,
)
from PySide6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QMenu, QMessageBox, QPushButton, QSlider,
)


STANDBY_STAR_RADIUS = 58
STANDBY_PLANET_SCALE = 1.08
EXPANDED_STAR_RADIUS = 19


ORBIT_COLORS = (
    ("highlightColor", "选中颜色（RGB）", "#ffc24f"),
    ("orbitColor", "未选中轨道颜色（RGB）", "#a6bcd3"),
)


APPEARANCE_CONTROLS = (
    ("standbySize", "待机尺寸", 65, 145, 100),
    ("expandedSize", "选中模式尺寸", 65, 145, 100),
    ("brightness", "星系整体亮度", 55, 145, 95),
    ("shadowLight", "行星阴影补光", 12, 60, 36),
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
        self._last_tick = monotonic()
        self._orbital_angles = []
        self._spin_time = 0.
        self.focused = 0
        self.targets = []
        self._appearance_preview = None
        self._hover_anchor = None
        self._hover_until = 0.0
        self._hover_rearm_at = None
        self.timer = QTimer(self, interval=33)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._advance)
        self.timer.start()
        area = app.primaryScreen().availableGeometry()
        self._anchor = area.bottomRight() - QPoint(147, 147)
        self._viewport_key = None
        self._sync_viewport()

    def _advance(self):
        now = monotonic()
        dt = min(now - self._last_tick, .12)
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
        self._sync_viewport()
        masses, _, axes, _ = self._planet_layout()
        for i, axis in enumerate(axes):
            if i == len(self._orbital_angles):
                self._orbital_angles.append((.22 + i*2.39996) % tau)
            self._orbital_angles[i] = (
                self._orbital_angles[i] + dt*orbital_speed(axis, masses[i])
            ) % tau
        self._spin_time += dt
        self.update()

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
        over_body = self.rect().contains(point) and self._body_at(point) is not None
        if over_body:
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
            extent = size * RING_EXTENT
            eccentricity = orbit_for(i).eccentricity
            axis = (outer + extent + 7) / (1 - eccentricity)
            axes.append(axis)
            outer = axis * (1 + eccentricity) + extent
        return masses, sizes, axes, outer

    def _sync_viewport(self):
        key = tuple(self.controls.contextTokens(i) for i in range(self.controls.windowCount))
        if key == self._viewport_key or self._dragging:
            return
        self._viewport_key = key
        outer = max(self._planet_layout(0)[3], self._planet_layout(1)[3])
        self._camera = max(620., 4*outer)
        self._resize_scene(outer)

    def _resize_scene(self, outer):
        # A stable anchor keeps growing orbits near the place the user dragged to.
        edge = outer * self._camera / (self._camera - outer) + 12
        half_size = 8 * ceil(max(135, edge, max(self._star_radius(0), self._star_radius(1))*2.45) / 8)
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

    def _draw_orbit(self, painter, index, axis, camera):
        e = self.expansion
        points = []
        for ux, uy, uz in guide_points(index):
            x, y, _ = project(axis*ux, axis*uy, axis*uz, camera)
            points.append(QPointF(x, y))
        selected = index == self.focused
        if selected:
            painter.setPen(self._selection_pen())
        else:
            color = QColor(self._orbit_colors["orbitColor"])
            intensity = self._appearance["brightness"] / 100
            color.setAlpha(round((14 + 34*e) * intensity))
            painter.setPen(QPen(color, self._appearance["orbitWidth"] / 10))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))

    def _selection_pen(self):
        color = QColor(self._orbit_colors["highlightColor"])
        color.setAlpha(round(14 + 216*self.expansion))
        width = .75 + (self._appearance["highlightWidth"]/10 - .75)*self.expansion
        return QPen(color, width)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        center = QPointF(self.width()/2, self.height()/2)
        p.translate(center)
        e = self.expansion
        star_radius = self._star_radius()
        _, radii, axes, _ = self._planet_layout()
        count = len(axes)
        camera = self._camera
        brightness = self._appearance["brightness"] / 100
        shadow_light = self._appearance["shadowLight"] / 100
        halo = star_radius * 2.45
        glow = QRadialGradient(0, 0, halo)
        for stop, color in (
            (0, QColor(255, 202, 125, 210)), (.40, QColor(255, 182, 83, 140)),
            (.46, QColor(255, 149, 62, 75)), (.64, QColor(233, 111, 44, 26)),
            (1, QColor(217, 91, 34, 0)),
        ):
            color.setAlpha(min(255, round(color.alpha() * brightness)))
            glow.setColorAt(stop, color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(), halo, halo)

        bodies = [(0., -1, 0., 0., star_radius, (0., 0., 1.))]
        selection_orbit = None
        for i in range(count):
            orbit = orbit_for(i)
            axis = axes[i]
            self._draw_orbit(p, i, axis, camera)
            mean = self._orbital_angles[i] if i < len(self._orbital_angles) else .22 + i*2.39996
            anomaly = orbit.anomaly(mean)
            x, y, z = orbit.position(anomaly, e, axis)
            sx, sy, scale = project(x, y, z, camera)
            distance = hypot(x, y, z)
            light = (-x/distance, -y/distance, -z/distance)
            radius = radii[i] * scale
            bodies.append((z, i, sx, sy, radius, light))
            if i == self.focused and e > .5:
                selection_orbit = orbit, anomaly, axis

        self.targets.clear()
        for _, i, x, y, radius, light in sorted(bodies):
            kind = 0 if i < 0 else 1 + i % 4
            spin = self._spin_time * (.055 if i < 0 else .16 + .022*(i % 4)) + kind
            ring = ring_state(i + 1, self._spin_time) if i >= 0 else None
            image, extent = sphere(kind, radius, self.devicePixelRatioF(), light, spin, i + 1,
                                   brightness=brightness, shadow_light=shadow_light,
                                   ring=ring)
            p.drawImage(QRectF(x-extent, y-extent, 2*extent, 2*extent), image)
            self.targets.append((center + QPointF(x, y), radius, i))
            if i == self.focused and e > .5:
                p.setPen(self._selection_pen())
                p.setBrush(Qt.BrushStyle.NoBrush)
                orbit, anomaly, axis = selection_orbit
                frame_radius = radius * (1 + (RING_EXTENT - 1) * ring[0]) + 4
                bounds = QRectF(x-frame_radius, y-frame_radius, 2*frame_radius, 2*frame_radius)
                angles = []
                # Put two arcs at the actual crossings of the orbit and frame.
                for direction in (-1, 1):
                    low, high = 0., 1.57
                    for _ in range(14):
                        step = (low + high) / 2
                        px, py, _ = project(*orbit.position(anomaly + direction*step, e, axis), camera)
                        if hypot(px - x, py - y) < frame_radius:
                            low = step
                        else:
                            high = step
                    angles.append(degrees(atan2(y - py, px - x)))
                turn = (angles[1] - angles[0]) % 360
                for angle in (*angles, angles[0] + turn/2, angles[1] + (360-turn)/2):
                    p.drawArc(bounds, round(angle*16)-350, 700)
        if e > .40:
            label = f"会话 {self.focused + 1} / {count}" if count else "点击恒星新建会话"
            width = p.fontMetrics().horizontalAdvance(label) + 22
            bounds = QRectF(-width/2, 83, width, 24)
            p.setOpacity((e-.40)/.60)
            p.setPen(QPen(QColor(204, 177, 138, 60), .8))
            p.setBrush(QColor(19, 22, 29, 213))
            p.drawRoundedRect(bounds, 12, 12)
            p.setPen(QColor("#f3d9b2"))
            p.drawText(bounds, Qt.AlignmentFlag.AlignCenter, label)
        p.end()

    def wheelEvent(self, event):
        if self.controls.windowCount:
            self.focused = (self.focused + (1 if event.angleDelta().y() < 0 else -1)) % self.controls.windowCount
            self.update()
        event.accept()

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
                    self.focused = index
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
            self.focused = min(self.focused, max(0, self.controls.windowCount - 1))
            self.update()
        else:
            QMessageBox.warning(self, "暂时无法删除", "请等待当前回复结束，或先停止生成。")
