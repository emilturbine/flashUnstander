"""Run the Windows Qt integration with isolated data and a simulated provider."""
import asyncio
import ctypes
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from flashunstander.app import Controller, Runtime
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


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with TemporaryDirectory() as directory:
        runtime = Runtime(Path(directory))
        desktop = DesktopIntegration(app)
        try:
            check_hotkey_conflict(desktop)
            manager = WindowManager(lambda bridge: Controller(app, bridge, runtime))
            desktop.showRequested.connect(manager.show_recent)
            desktop.newWindowRequested.connect(manager.create_window)
            manager.create_window()
            for _ in range(3):
                manager.windows[-1][0].newWindowRequested.emit()
            windows = manager.windows
            assert len(windows) == 4
            wait_for(app, lambda: all(not item[2].busy for item in windows), "window startup")
            assert len({item[3].conversation_id for item in windows}) == 4
            last, _, last_bridge, _ = windows[-1]
            original_color = last.property("color")
            last.setProperty("lightTheme", True)
            assert last.property("color") != original_color
            last.close()
            assert not last.isVisible()
            manager.last_window = last
            desktop.showRequested.emit()
            assert last.isVisible()
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
            print("Four-window streaming, cancellation, isolation, theme, restore and shortcut conflict passed.")
        finally:
            desktop.close()
            runtime.shutdown()


if __name__ == "__main__":
    main()
