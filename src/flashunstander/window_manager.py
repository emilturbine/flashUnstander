"""Manage independent QML windows; the caller supplies shared-service controllers."""
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from .window_bridge import WindowBridge


class WindowManager(QObject):
    windowCreated = Signal(object)
    windowsChanged = Signal()

    def __init__(self, controller_factory, parent=None, qml_path=None):
        super().__init__(parent)
        self.controller_factory = controller_factory
        self.qml_path = Path(qml_path) if qml_path else Path(__file__).parent / "qml" / "Main.qml"
        self.windows = []
        self.last_window = None

    def create_window(self, source=None, *, conversation_id=None, visible=True):
        bridge = WindowBridge()
        controller = (self.controller_factory(bridge) if conversation_id is None
                      else self.controller_factory(bridge, conversation_id))
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.load(QUrl.fromLocalFile(str(self.qml_path.resolve())))
        if not engine.rootObjects():
            raise RuntimeError("无法加载悬浮窗口")
        window = engine.rootObjects()[0]
        window.newWindowRequested.connect(lambda: self.create_window(window))
        window.activeChanged.connect(lambda: self._activated(window, bridge))
        bridge.replyCompleted.connect(lambda: bridge.register_reply_completion(
            window.isVisible() and window.isActive()
            and window.windowState() != Qt.WindowState.WindowMinimized
        ))
        window.visibleChanged.connect(self._visibility_changed)
        self._place(window, source or self.last_window)
        self.windows.append((window, engine, bridge, controller))
        self.last_window = window
        self.windowCreated.emit(window)
        if visible:
            window.show()
            window.requestActivate()
        else:
            self.windowsChanged.emit()
        return window

    def delete_window(self, index):
        window, engine, bridge, controller = self.windows[index]
        if bridge.busy:
            return False
        controller.delete_conversation()
        self.windows.pop(index)
        if self.last_window is window:
            self.last_window = self.windows[-1][0] if self.windows else None
        window.hide()
        engine.deleteLater()
        controller.deleteLater()
        bridge.deleteLater()
        self.windowsChanged.emit()
        return True

    def _place(self, window, source):
        screen = source.screen() if source else QGuiApplication.primaryScreen()
        area = screen.availableGeometry().adjusted(8, 8, -8, -8)
        # Leave clearance around both the bundled and custom window designs.
        size = QSize(window.width() + 16, window.height() + 40)
        max_x = max(area.left(), area.right() - size.width() + 1)
        max_y = max(area.top(), area.bottom() - size.height() + 1)
        occupied = [item[0].frameGeometry() for item in self.windows
                    if item[0].isVisible()]
        if source:
            base = source.frameGeometry()
            candidates = [
                (base.right() + 12, base.top()), (base.left() - size.width() - 12, base.top()),
                (base.left(), base.bottom() + 12), (base.left(), base.top() - size.height() - 12),
            ]
        else:
            candidates = [(area.center().x() - size.width() // 2,
                           area.center().y() - size.height() // 2)]
        columns = list(range(area.left(), max_x, size.width() + 12)) + [max_x]
        rows = list(range(area.top(), max_y, size.height() + 12)) + [max_y]
        candidates.extend((x, y) for y in rows for x in columns)
        for x, y in candidates:
            point = QPoint(min(max_x, max(area.left(), x)), min(max_y, max(area.top(), y)))
            if not any(rect.intersects(QRect(point, size)) for rect in occupied):
                window.setFramePosition(point)
                return
        # A full screen still gets a visible offset for the new title bar.
        used_positions = {(rect.x(), rect.y()) for rect in occupied}
        for y in range(area.top(), max_y + 1, 28):
            for x in range(area.left(), max_x + 1, 28):
                if (x, y) not in used_positions:
                    window.setFramePosition(QPoint(x, y))
                    return
        window.setFramePosition(QPoint(area.left(), area.top()))

    def _activated(self, window, bridge):
        if window.isActive():
            self.last_window = window
            if window.isVisible() and window.windowState() != Qt.WindowState.WindowMinimized:
                bridge.mark_reply_read()

    @Slot(bool)
    def _visibility_changed(self, visible):
        self.windowsChanged.emit()

    def show_recent(self):
        window = self.last_window or self.create_window()
        self._show_window(window)
        window.raise_()
        window.requestActivate()

    def show_all(self):
        for window, _, _, _ in self.windows:
            self._show_window(window)

    @staticmethod
    def _show_window(window):
        if window.windowState() == Qt.WindowState.WindowMinimized:
            window.showNormal()
        else:
            window.show()
