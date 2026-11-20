"""Run the Windows Qt integration with isolated data and a simulated provider."""
import asyncio
import ctypes
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtQuick import QQuickItem
import win32con
import win32gui
import win32api

from flashunstander.app import Controller, Runtime
from flashunstander.control_ball import ControlBall
from flashunstander.control_bridge import ControlBridge
from flashunstander.desktop import DesktopIntegration
from flashunstander.provider import StreamEvent
from flashunstander.window_manager import WindowManager


class FakeClient:
    def __init__(self, **kwargs):
        pass

    async def close(self):
        pass


async def fake_stream(client, provider, model, messages, max_tokens):
    yield StreamEvent("text", f"回复 {messages[-1]['content']}")
    await asyncio.sleep(2)
    yield StreamEvent("completed", input_tokens=5, output_tokens=7)


def wait_for(app, predicate, label):
    deadline = monotonic() + 10
    while not predicate():
        assert monotonic() < deadline, label
        app.processEvents()
        QTest.qWait(15)


def check_hotkey_conflict(desktop):
    user32 = ctypes.windll.user32
    modifiers = 0x0007  # Ctrl+Alt+Shift
    competing_id = 0x4656
    current_key, competing_key = 0x78, 0x79  # F9 and F10
    assert desktop.register_hotkey(modifiers, current_key)
    assert user32.RegisterHotKey(None, competing_id, modifiers, competing_key)
    try:
        assert not desktop.register_hotkey(modifiers, competing_key)
        # Registering the old key under another ID must still fail.
        previous_key_probe = 0x4657
        if user32.RegisterHotKey(None, previous_key_probe, modifiers, current_key):
            user32.UnregisterHotKey(None, previous_key_probe)
            raise AssertionError("previous shortcut was not restored")
    finally:
        user32.UnregisterHotKey(None, competing_id)
    assert desktop.register_hotkey(modifiers, competing_key)


def check_native_windows(ball, window):
    ball_handle = int(ball.winId())
    left, top, right, bottom = win32gui.GetWindowRect(ball_handle)
    assert win32gui.WindowFromPoint(((left + right) // 2, (top + bottom) // 2)) == ball_handle
    assert win32gui.WindowFromPoint((left + 1, top + 1)) != ball_handle

    window_handle = int(window.winId())
    style = win32gui.GetWindowLong(window_handle, win32con.GWL_STYLE)
    assert style & win32con.WS_CAPTION == 0
    assert window.findChild(QQuickItem, "windowDragRegion").width() > 0
    def visual_children(item):
        for child in item.childItems():
            yield child
            yield from visual_children(child)

    assert sum(item.objectName() == "windowResizeRegion"
               for item in visual_children(window.contentItem())) == 8


def check_ball_drag(ball, controls):
    start = ball.pos()
    local = QPointF(ball.rect().center())
    global_start = QPointF(ball.mapToGlobal(ball.rect().center()))
    delta = QPointF(-70, -50)
    left = Qt.MouseButton.LeftButton
    none = Qt.MouseButton.NoButton
    for kind, button, buttons, position in [
        (QEvent.Type.MouseButtonPress, left, left, global_start),
        (QEvent.Type.MouseMove, none, left, global_start + delta),
        (QEvent.Type.MouseButtonRelease, left, none, global_start + delta),
    ]:
        QApplication.sendEvent(ball, QMouseEvent(kind, local, position, button, buttons,
                                                Qt.KeyboardModifier.NoModifier))
    assert ball.pos() == start + delta.toPoint()
    assert controls.windowCount == 0, "Dragging must not open a chat window"


def check_scroll(app, window, bridge):
    prompt = window.findChild(QQuickItem, "prompt")
    prompt_scroll = window.findChild(QQuickItem, "promptScroll").property("contentItem")
    answer_scroll = window.findChild(QQuickItem, "answerScroll").property("contentItem")
    prompt.forceActiveFocus()
    long_text = "\n".join(f"第 {index} 行" for index in range(80))
    prompt.setProperty("text", long_text)
    prompt.setProperty("cursorPosition", len(long_text))
    bridge.update_state(answer=long_text)
    wait_for(app, lambda: all(item.property("contentHeight") > item.property("height")
                             for item in (prompt_scroll, answer_scroll)), "scrollable text")
    wait_for(app, lambda: prompt_scroll.property("contentY") > 0, "input follows caret")
    answer_scroll.setProperty("contentY", 50)
    assert answer_scroll.property("contentY") == 50
    prompt.setProperty("text", "")
    bridge.update_state(answer="")


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with TemporaryDirectory() as directory:
        runtime = Runtime(Path(directory))
        desktop = DesktopIntegration(app)
        try:
            check_hotkey_conflict(desktop)
            assert desktop.register_hotkey(), "Alt+Shift+W registration"
            manager = WindowManager(lambda bridge: Controller(app, bridge, runtime))
            controls = ControlBridge(manager, app.quit)
            ball = ControlBall(app, controls)
            desktop.showRequested.connect(manager.show_recent)
            desktop.newWindowRequested.connect(manager.create_window)
            ball.show()
            assert controls.windowCount == 0
            assert ball.mask().contains(ball.rect().center())
            assert not ball.mask().contains(QPoint(0, 0))
            check_ball_drag(ball, controls)
            win32api.PostThreadMessage(win32api.GetCurrentThreadId(), win32con.WM_HOTKEY,
                                       desktop._hotkey_id, (0x57 << 16) | 0x0005)
            wait_for(app, lambda: controls.windowCount == 1, "global hotkey opened chat")
            for _ in range(3):
                manager.windows[-1][0].newWindowRequested.emit()
            windows = manager.windows
            assert len(windows) == 4
            wait_for(app, lambda: all(not item[2].busy for item in windows), "window startup")
            assert len({item[3].conversation_id for item in windows}) == 4
            assert controls.visibleCount == 4
            assert len({(item[0].x(), item[0].y()) for item in windows}) == 4
            for window, *_ in windows:
                assert not window.flags() & Qt.WindowType.WindowStaysOnTopHint
            last, _, last_bridge, _ = windows[-1]
            check_native_windows(ball, last)
            check_scroll(app, last, last_bridge)
            original_color = last.property("color")
            last.setProperty("lightTheme", True)
            assert last.property("color") != original_color
            last.close()
            assert not last.isVisible()
            assert controls.visibleCount == 3
            manager.last_window = last
            desktop.showRequested.emit()
            assert last.isVisible()
            assert controls.visibleCount == 4
            with (
                patch("flashunstander.app.AsyncOpenAI", FakeClient),
                patch("flashunstander.app.stream_response", fake_stream),
                patch("flashunstander.app.keyring.get_password", return_value="test"),
            ):
                for index, (_, _, bridge, _) in enumerate(windows):
                    assert bridge.send(f"第{index}问", "")
                wait_for(app, lambda: all("回复" in item[2].answer for item in windows[:3]), "parallel streams")
                assert last_bridge.busy and "回复" not in last_bridge.answer
                windows[0][2].stop()
                wait_for(app, lambda: windows[0][2].status == "已停止", "cancel")
                wait_for(app, lambda: "回复 第3问" in last_bridge.answer, "dispatch after cancel")
                wait_for(app, lambda: all(not item[2].busy for item in windows), "completion")
                for index, (_, _, bridge, _) in enumerate(windows):
                    assert f"回复 第{index}问" in bridge.answer
                    assert all(f"回复 第{other}问" not in bridge.answer for other in range(4) if other != index)
                assert "输入 5" in last_bridge.metrics and "输出 7" in last_bridge.metrics
            print("Frameless controls, ball drag/hit test, hotkey routing, scrolling and four-window streaming passed.")
        finally:
            desktop.close()
            runtime.shutdown()


if __name__ == "__main__":
    main()
