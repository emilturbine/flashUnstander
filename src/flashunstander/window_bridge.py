"""Stable Qt boundary between a window and the conversation controller."""
from time import monotonic

from PySide6.QtCore import QObject, Property, Signal, Slot

from .provider import supports_search, supports_thinking


class WindowBridge(QObject):
    replyCompleted = Signal()
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
        self.unread_reply = False
        self._aurora_started = 0.
        self._aurora_until = 0.
        self._aurora_entry_level = 0.
        self._aurora_exit_level = 1.
        self._thinking = False
        self._search = False
        self.send_handler = None

    def register_reply_completion(self, in_foreground):
        now = monotonic()
        self._aurora_entry_level = self._aurora_opacity(now)
        self._aurora_started = now
        self.unread_reply = not in_foreground
        self._aurora_until = now + 5
        self._aurora_exit_level = 1.

    def mark_reply_read(self):
        if self.unread_reply:
            now = monotonic()
            self._aurora_exit_level = self._aurora_opacity(now)
            self._aurora_until = now + 1
            self.unread_reply = False

    @staticmethod
    def _fade(progress):
        progress = max(0., min(1., progress))
        return progress * progress * (3 - 2 * progress)

    def _aurora_opacity(self, now):
        if self.unread_reply or now < self._aurora_until - 1:
            fade_in = self._fade(now - self._aurora_started)
            return self._aurora_entry_level + (1 - self._aurora_entry_level) * fade_in
        return self._aurora_exit_level * self._fade(self._aurora_until - now)

    @property
    def aurora_opacity(self):
        return self._aurora_opacity(monotonic())

    @property
    def aurora_active(self):
        return self.unread_reply or monotonic() < self._aurora_until

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
