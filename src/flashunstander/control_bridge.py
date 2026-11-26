"""Commands and window state shared by interchangeable desktop launchers."""

from PySide6.QtCore import QObject, Property, Signal, Slot


class ControlBridge(QObject):
    windowsChanged = Signal()
    conversationDeleted = Signal(str)

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

    def planetAuroraOpacity(self, index):
        return self._manager.windows[index][2].aurora_opacity

    def conversationId(self, index):
        return self._manager.windows[index][3].conversation_id

    def contextTokens(self, index):
        return self._manager.windows[index][2].context_tokens

    @Slot(int)
    def openWindow(self, index):
        if 0 <= index < self.windowCount:
            window = self._manager.windows[index][0]
            self._manager._show_window(window)
            window.raise_()
            window.requestActivate()

    def canDeleteWindow(self, index):
        return 0 <= index < self.windowCount and not self._manager.windows[index][2].busy

    def deleteWindow(self, index):
        if not self.canDeleteWindow(index):
            return False
        identifier = self.conversationId(index)
        deleted = self._manager.delete_window(index)
        if deleted and identifier:
            self.conversationDeleted.emit(identifier)
        return deleted

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
