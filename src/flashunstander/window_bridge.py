"""Stable Qt boundary between a window and the conversation controller."""
from PySide6.QtCore import QObject, Property, Signal, Slot


class WindowBridge(QObject):
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
        self.send_handler = None

    @Property(str, notify=stateChanged)
    def provider(self):
        return self._provider

    @Property(str, notify=stateChanged)
    def model(self):
        return self._model

    def set_settings(self, provider, model):
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
