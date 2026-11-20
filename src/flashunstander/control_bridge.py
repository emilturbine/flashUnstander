"""Commands and window state shared by interchangeable desktop launchers."""

from PySide6.QtCore import QObject, Property, Signal, Slot


class ControlBridge(QObject):
    windowsChanged = Signal()

    def __init__(self, manager, quit_app, open_settings=None):
        super().__init__()
        self._manager = manager
        self._quit_app = quit_app
        self._open_settings = open_settings
        manager.windowsChanged.connect(self.windowsChanged)

    @Property(int, notify=windowsChanged)
    def windowCount(self):
        return len(self._manager.windows)

    @Property(int, notify=windowsChanged)
    def visibleCount(self):
        return sum(window.isVisible() for window, *_ in self._manager.windows)

    @Slot()
    def openRecent(self):
        self._manager.show_recent()

    @Slot()
    def openNew(self):
        self._manager.create_window()

    @Slot()
    def showAll(self):
        self._manager.show_all()

    @Slot()
    def openSettings(self):
        if self._open_settings:
            self._open_settings()

    @Slot()
    def quit(self):
        self._quit_app()
