"""A small desktop launcher with a circular native hit region."""

from math import exp, hypot, tau
from time import monotonic

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QRegion, QPainter, QColor, QRadialGradient, QPen, QPolygonF
from .cosmic import sphere
from .orbit import (
    PLANET_MATERIALS, guide_points, orbit_for, orbital_speed, planet_mass_ratio,
    planet_radius, project,
)
from PySide6.QtWidgets import QApplication, QMenu, QPushButton


STANDBY_STAR_RADIUS = 54
EXPANDED_STAR_RADIUS = 19


class ControlBall(QPushButton):
    def __init__(self, app, controls, *, shortcut_available=True):
        super().__init__("F")
        self.controls = controls
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
        self.timer = QTimer(self, interval=33)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._advance)
        self.timer.start()
        area = app.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 12, area.bottom() - self.height() - 12)

    def _advance(self):
        now = monotonic()
        dt = min(now - self._last_tick, .12)
        self._last_tick = now
        target = float(self.underMouse())
        # Closed-form critically damped spring. Retain velocity on reversal.
        offset = self.expansion - target
        frequency = 10.
        impulse = self._velocity + frequency*offset
        decay = exp(-frequency*dt)
        self.expansion = target + (offset + impulse*dt)*decay
        self._velocity = (self._velocity - frequency*impulse*dt)*decay
        masses, _, axes, _ = self._planet_layout()
        for i, axis in enumerate(axes):
            if i == len(self._orbital_angles):
                self._orbital_angles.append((.22 + i*2.39996) % tau)
            self._orbital_angles[i] = (
                self._orbital_angles[i] + dt*orbital_speed(axis, masses[i])
            ) % tau
        self._spin_time += dt
        self.update()

    def _star_radius(self):
        return STANDBY_STAR_RADIUS + self.expansion * (EXPANDED_STAR_RADIUS - STANDBY_STAR_RADIUS)

    def _planet_layout(self):
        count = self.controls.windowCount
        masses, sizes = [], []
        for i in range(count):
            material = PLANET_MATERIALS[i % len(PLANET_MATERIALS)]
            tokens = self.controls.contextTokens(i)
            masses.append(planet_mass_ratio(planet_radius(tokens, 0, material), material))
            sizes.append(planet_radius(tokens, self.expansion, material))
        axes = []
        outer = self._star_radius()
        for i, size in enumerate(sizes):
            extent = size * (1.83 if i % 4 == 2 else 1)
            eccentricity = orbit_for(i).eccentricity
            axis = (outer + extent + 7) / (1 - eccentricity)
            axes.append(axis)
            outer = axis * (1 + eccentricity) + extent
        return masses, sizes, axes, outer

    def _draw_orbit(self, painter, index, axis):
        e = self.expansion
        points = []
        for ux, uy, uz in guide_points(index):
            x, y, _ = project(axis*ux, axis*uy, axis*uz)
            points.append(QPointF(x, y))
        selected = index == self.focused
        color = QColor(223, 181, 119) if selected else QColor(166, 188, 211)
        color.setAlpha(int(14 + (58 if selected else 34)*e))
        painter.setPen(QPen(color, .75))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(points))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        center = QPointF(self.width()/2, self.height()/2)
        p.translate(center)
        e = self.expansion
        star_radius = self._star_radius()
        _, radii, axes, outer = self._planet_layout()
        count = len(axes)
        fit = min(1., 113 / outer)
        star_radius *= fit
        halo = star_radius * 2.45
        glow = QRadialGradient(0, 0, halo)
        for stop, color in (
            (0, QColor(255, 202, 125, 210)), (.40, QColor(255, 182, 83, 140)),
            (.46, QColor(255, 149, 62, 75)), (.64, QColor(233, 111, 44, 26)),
            (1, QColor(217, 91, 34, 0)),
        ):
            glow.setColorAt(stop, color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(), halo, halo)

        bodies = [(0., -1, 0., 0., star_radius, (0., 0., 1.))]
        for i in range(count):
            orbit = orbit_for(i)
            axis = axes[i] * fit
            self._draw_orbit(p, i, axis)
            mean = self._orbital_angles[i] if i < len(self._orbital_angles) else .22 + i*2.39996
            x, y, z = orbit.position(orbit.anomaly(mean), e, axis)
            sx, sy, scale = project(x, y, z)
            distance = hypot(x, y, z)
            light = (-x/distance, -y/distance, -z/distance)
            radius = radii[i] * fit * scale
            bodies.append((z, i, sx, sy, radius, light))

        self.targets.clear()
        for _, i, x, y, radius, light in sorted(bodies):
            kind = 0 if i < 0 else 1 + i % 4
            spin = self._spin_time * (.055 if i < 0 else .16 + .022*(i % 4)) + kind
            image, extent = sphere(kind, radius, self.devicePixelRatioF(), light, spin, i + 1)
            p.drawImage(QRectF(x-extent, y-extent, 2*extent, 2*extent), image)
            self.targets.append((center + QPointF(x, y), radius, i))
            if i == self.focused and e > .5:
                p.setPen(QPen(QColor(238, 192, 126, int(180*e)), .85))
                p.setBrush(Qt.BrushStyle.NoBrush)
                bounds = QRectF(x-radius-4, y-radius-4, 2*radius+8, 2*radius+8)
                for quadrant in range(4):
                    p.drawArc(bounds, quadrant*1440+240, 700)
        if e > .40:
            label = f"会话 {self.focused + 1} / {count}" if count else "点击空白处新建会话"
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
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = None
            if self._dragging:
                self._dragging = False
                event.accept()
                return
            for pos, radius, index in reversed(self.targets):
                if hypot(event.position().x() - pos.x(), event.position().y() - pos.y()) <= radius + 3:
                    self.setDown(False)
                    if index < 0:
                        self.controls.openSettings()
                    else:
                        self.focused = index
                        self.controls.openWindow(index)
                    event.accept()
                    return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("打开最近窗口", self.controls.openRecent)
        menu.addAction("新建问答窗", self.controls.openNew)
        menu.addAction("显示全部窗口", self.controls.showAll).setEnabled(self.controls.windowCount > 0)
        menu.addAction("设置", self.controls.openSettings)
        menu.addSeparator()
        menu.addAction("退出", self.controls.quit)
        menu.exec(event.globalPos())
