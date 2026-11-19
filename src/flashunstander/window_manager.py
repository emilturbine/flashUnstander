"""Manage independent QML windows; the caller supplies shared-service controllers."""
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtQml import QQmlApplicationEngine

from .window_bridge import WindowBridge


class WindowManager(QObject):
    windowCreated = Signal(object)

    def __init__(self, controller_factory, parent=None, qml_path=None):
        super().__init__(parent)
        self.controller_factory = controller_factory
        self.qml_path = Path(qml_path) if qml_path else Path(__file__).parent / "qml" / "Main.qml"
        self.windows = []
        self.last_window = None

    def create_window(self):
        bridge = WindowBridge()
        controller = self.controller_factory(bridge)
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty("bridge", bridge)
        engine.load(QUrl.fromLocalFile(str(self.qml_path.resolve())))
        if not engine.rootObjects():
            raise RuntimeError("无法加载悬浮窗口")
        window = engine.rootObjects()[0]
        window.newWindowRequested.connect(self.create_window)
        window.activeChanged.connect(lambda: self._activated(window))
        self.windows.append((window, engine, bridge, controller))
        self.last_window = window
        self.windowCreated.emit(window)
        return window

    def _activated(self, window):
        if window.isActive():
            self.last_window = window

    def show_recent(self):
        window = self.last_window or self.create_window()
        window.show()
        window.raise_()
        window.requestActivate()

    def show_all(self):
        for window, _, _, _ in self.windows:
            window.show()
