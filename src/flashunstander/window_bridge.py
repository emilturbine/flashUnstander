"""Stable Qt boundary between a window and the conversation controller."""
from PySide6.QtCore import QObject, Property, Signal, Slot

from .provider import supports_search, supports_thinking


class WindowBridge(QObject):
    messagesChanged = Signal()
    sendRequested = Signal(str, str)
    stopRequested = Signal()
    settingsRequested = Signal()
    settingsSaved = Signal(str, str, str)
    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._answer = ""
        self._status = "就绪"
        self._metrics = ""
        self._busy = False
        self._provider = "deepseek"
        self._model = "deepseek-flash"
        self._messages = []
        self.context_tokens = 0
        self._thinking = False
        self._search = False
        self.send_handler = None

    @Property("QVariantList", notify=messagesChanged)
    def messages(self):
        return self._messages

    def set_messages(self, messages):
        self._messages = list(messages)
        self.messagesChanged.emit()

    @Property(bool, notify=stateChanged)
    def thinkingAvailable(self):
        return supports_thinking(self._provider, self._model)

    @Property(bool, notify=stateChanged)
    def searchAvailable(self):
        return supports_search(self._provider, self._model)

    @Property(bool, notify=stateChanged)
    def thinkingEnabled(self):
        return self._thinking and self.thinkingAvailable

    @Property(bool, notify=stateChanged)
    def searchEnabled(self):
        return self._search and self.searchAvailable

    @Slot(bool)
    def setThinking(self, enabled):
        self._thinking = enabled and self.thinkingAvailable
        self.stateChanged.emit()

    @Slot(bool)
    def setSearch(self, enabled):
        self._search = enabled and self.searchAvailable
        self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def provider(self):
        return self._provider

    @Property(str, notify=stateChanged)
    def model(self):
        return self._model

    def set_settings(self, provider, model):
        if (provider, model) != (self._provider, self._model):
            self._thinking = self._search = False
        self._provider = provider
        self._model = model
        self.stateChanged.emit()

    @Property(str, notify=stateChanged)
    def answer(self):
        return self._answer

    @Property(str, notify=stateChanged)
    def status(self):
        return self._status

    @Property(str, notify=stateChanged)
    def metrics(self):
        return self._metrics

    @Property(bool, notify=stateChanged)
    def busy(self):
        return self._busy

    def update_state(self, *, answer=None, status=None, metrics=None, busy=None):
        if answer is not None:
            self._answer = answer
        if status is not None:
            self._status = status
        if metrics is not None:
            self._metrics = metrics
        if busy is not None:
            self._busy = busy
        self.stateChanged.emit()

    @Slot(str, str, result=bool)
    def send(self, text, image_path):
        if not (text.strip() or image_path) or self._busy or self.send_handler is None:
            return False
        return bool(self.send_handler(text, image_path))

    @Slot()
    def stop(self):
        self.stopRequested.emit()

    @Slot()
    def openSettings(self):
        self.settingsRequested.emit()

    @Slot(str, str, str)
    def saveSettings(self, provider, model, key):
        self.settingsSaved.emit(provider, model.strip(), key)
