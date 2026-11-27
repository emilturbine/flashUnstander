"""Windows global shortcut and system tray integration.

Create and use DesktopIntegration on the Qt application thread. A failed hotkey
registration leaves the previous binding intact, so callers can offer a retry.
"""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal, QAbstractNativeEventFilter
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG" or event_type == b"windows_dispatcher_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == 0x0312 and msg.wParam == self.owner._hotkey_id:
                self.owner.hotkeyRequested.emit()
                return True, 0
        return False, 0


class DesktopIntegration(QObject):
    showRequested = Signal()
    hotkeyRequested = Signal()
    quitRequested = Signal()

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self._hotkey_id = 0x4655
        self._registered = False
        self._filter = _HotkeyFilter(self)
        self.app.installNativeEventFilter(self._filter)
        self.menu = QMenu()
        for label, signal in (("显示窗口", self.showRequested),
                              ("退出", self.quitRequested)):
            action = QAction(label, self.menu)
            action.triggered.connect(lambda checked=False, target=signal: target.emit())
            self.menu.addAction(action)
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#4361a8"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), 0x84, "F")
        painter.end()
        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("flashUnstander")
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showRequested.emit()

    def add_topmost_toggle(self, checked, on_toggled):
        action = QAction("星系始终置顶", self.menu)
        action.setCheckable(True)
        action.setChecked(checked)
        action.toggled.connect(on_toggled)
        self.menu.insertAction(self.menu.actions()[-1], action)
        return action

    def register_hotkey(self, modifiers=0x0005, key=0x57):
        """Register a Win32 modifier mask and virtual key; default Alt+Shift+W.

        Returns False when unavailable. The prior binding is restored if possible.
        """
        if sys.platform != "win32":
            return False
        user32 = ctypes.windll.user32
        previous = getattr(self, "_binding", None)
        if self._registered:
            user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False
        if user32.RegisterHotKey(None, self._hotkey_id, modifiers | 0x4000, key):
            self._registered = True
            self._binding = (modifiers, key)
            return True
        if previous and user32.RegisterHotKey(None, self._hotkey_id, previous[0] | 0x4000, previous[1]):
            self._registered = True
        return False

    def close(self):
        if self._registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False
        self.app.removeNativeEventFilter(self._filter)
        self.tray.hide()
