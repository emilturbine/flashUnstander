"""A translucent, non-interactive star field behind the launcher."""
from math import ceil, hypot, sin
from random import Random
from time import monotonic

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget


class Starfield(QWidget):
    def __init__(self, opacity):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.WindowDoesNotAcceptFocus
                         | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.opacity = opacity
        self._view = (0., 0., 0., 0.)
        self._static_view = self._view
        self._static_key = None
        self._static_background = None
        rng = Random(1987)
        self.dust = []
        self.stars = []
        tinted = {
            i: rng.choice(((255, 213, 155), (255, 180, 138), (161, 198, 255)))
            for i in rng.sample(range(504), 25)
        }
        for i in range(504):
            x = rng.uniform(-.94, .94)
            y = rng.gauss(-x*.34, .15) if i < 364 else rng.uniform(-.82, .82)
            fade = max(0., 1 - hypot(x, y)**2)
            if fade > 0:
                self.stars.append((x, y, rng.random(), fade, rng.uniform(0, 6.28),
                                   tinted.get(i, (220, 234, 255))))
        depths = Random(2879)
        self.depths = [depths.uniform(70, 160) if i % 5 == 0 else depths.uniform(450, 1800)
                       for i in range(len(self.stars))]
        self._dim_stars = []
        self._bright_stars = []
        for star, distance in zip(self.stars, self.depths):
            (self._bright_stars if star[2] > .94 else self._dim_stars).append((star, distance))
        for i in range(13):
            x = (i - 6) / 8
            self.dust.append((x, -.36*x + rng.uniform(-.1, .1), rng.uniform(.09, .22)))

    def set_view(self, strength, x, y, z):
        view = (strength, x*strength, y*strength, z*strength)
        if view != self._view:
            self._view = view
            self.update()

    def _project(self, x, y, distance):
        strength, cx, cy, cz = self._view
        factor = (1 + .16*strength) / max(distance + cz, distance * .45)
        return (x*distance - cx)*factor, (y*distance - cy)*factor

    def _static_layer(self, scale):
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), ratio, self.opacity)
        movement = [abs(a-b) for a, b in zip(self._view, self._static_view)]
        estimated_pixel_delta = scale * (.16*movement[0] + sum(movement[1:])/70)
        if self._static_key == key and estimated_pixel_delta < .42:
            return self._static_background

        self._static_key = key
        self._static_view = self._view
        layer = QPixmap(ceil(self.width()*ratio), ceil(self.height()*ratio))
        layer.setDevicePixelRatio(ratio)
        layer.fill(Qt.GlobalColor.transparent)
        painter = QPainter(layer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width()/2, self.height()/2)
        painter.setPen(Qt.PenStyle.NoPen)
        for i, (x, y, radius) in enumerate(self.dust):
            x, y = self._project(x, y, 2600.)
            center = QPointF(x*scale, y*scale)
            radius *= scale * (1 + .16*self._view[0])
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0, QColor(112, 137, 207, round(25*self.opacity)) if i % 3 else QColor(158, 126, 199, round(26*self.opacity)))
            glow.setColorAt(1, QColor(110, 123, 185, 0))
            painter.setBrush(glow)
            painter.drawEllipse(center, radius, radius)

        for (x, y, magnitude, fade, _, color), distance in self._dim_stars:
            x, y = self._project(x, y, distance)
            if self._view[0]:
                fade = max(0., 1 - x*x - y*y)
            if fade:
                alpha = min(255, round((54 + 201*magnitude)*fade*self.opacity))
                painter.setBrush(QColor(*color, alpha))
                radius = (.45 + .8*magnitude)*.8
                painter.drawEllipse(QPointF(x*scale, y*scale), radius, radius)
        painter.end()
        self._static_background = layer
        return layer

    def paintEvent(self, event):
        scale = min(self.width(), self.height()) / 2
        background = self._static_layer(scale)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, background)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width()/2, self.height()/2)
        time = monotonic()
        for (x, y, magnitude, fade, phase, color), distance in self._bright_stars:
            x, y = self._project(x, y, distance)
            if self._view[0]:
                fade = max(0., 1 - x*x - y*y)
            if not fade:
                continue
            center = QPointF(x*scale, y*scale)
            pulse = .66 + .34*sin(time*(.9 + magnitude) + phase)
            alpha = min(255, round((54 + 201*magnitude)*fade*pulse*self.opacity))
            painter.setPen(Qt.PenStyle.NoPen)
            halo = QRadialGradient(center, 5.)
            halo.setColorAt(0, QColor(*color, alpha//2))
            halo.setColorAt(1, QColor(*color, 0))
            painter.setBrush(halo)
            painter.drawEllipse(center, 5., 5.)
            painter.setPen(QPen(QColor(*color, alpha//2), .65))
            painter.drawLine(center-QPointF(3, 0), center+QPointF(3, 0))
            painter.drawLine(center-QPointF(0, 3), center+QPointF(0, 3))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(*color, alpha))
            radius = (.45 + .8*magnitude)*1.2
            painter.drawEllipse(center, radius, radius)
        painter.end()
