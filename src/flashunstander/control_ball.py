"""A small desktop launcher with a circular native hit region."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QMenu, QPushButton


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
        self.setAccessibleName("打开 flashUnstander 问答")
        self.setWindowTitle("flashUnstander 中控")
        self.clicked.connect(controls.openRecent)
        controls.windowsChanged.connect(self._refresh_tooltip)
        self._refresh_tooltip()
        self.setFixedSize(42, 42)
        # The mask applies to both painting and native mouse hit testing.
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        self.setStyleSheet(
            "QPushButton { background: #35569f; color: white; border: 1px solid #8fa8e5;"
            " border-radius: 21px; font-size: 18px; font-weight: bold; }"
            "QPushButton:hover { background: #476cb8; }"
        )
        area = app.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 12, area.bottom() - self.height() - 12)

    def _refresh_tooltip(self):
        shortcut = "Alt+Shift+W 打开窗口" if self.shortcut_available else "Alt+Shift+W 注册失败"
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
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.addAction("打开最近窗口", self.controls.openRecent)
        menu.addAction("新建问答窗", self.controls.openNew)
        menu.addAction("显示全部窗口", self.controls.showAll).setEnabled(self.controls.windowCount > 0)
        menu.addSeparator()
        menu.addAction("退出", self.controls.quit)
        menu.exec(event.globalPos())
