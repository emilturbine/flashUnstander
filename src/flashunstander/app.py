"""Desktop entry point and bridge to the asynchronous conversation service."""
import asyncio
import base64
import json
import mimetypes
import os
from pathlib import Path
import threading
import time
from functools import lru_cache

import keyring
from openai import AsyncOpenAI
from PySide6.QtCore import QObject, Signal, QUrl, QTimer, QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from .provider import stream_response
from .scheduler import RequestScheduler
from .service import ConversationService
from .storage import Store
from .window_bridge import WindowBridge
from .window_manager import WindowManager
from .desktop import DesktopIntegration


@lru_cache(maxsize=1024)
def count_tokens(text):
    # UTF-8 bytes give a conservative estimate without fetching tokenizer data.
    return len(text.encode("utf-8"))


class Runtime(QObject):
    settingsChanged = Signal(str, str)

    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config_path = self.directory / "settings.json"
        self.config = {"provider": "deepseek", "model": "deepseek-flash", "max_output_tokens": 2048, "hotkey": "Alt+Space"}
        if self.config_path.exists():
            try:
                self.config.update(json.loads(self.config_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.ready = asyncio.run_coroutine_threadsafe(self._initialize(), self.loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _initialize(self):
        self.store = Store(self.directory / "history.db")
        self.store.recover_interrupted()
        self.service = ConversationService(self.store, RequestScheduler())

    def shutdown(self):
        async def close():
            await asyncio.wrap_future(self.ready)
            await self.service.scheduler.close()
            self.store.close()
        future = asyncio.run_coroutine_threadsafe(close(), self.loop)
        try:
            future.result(timeout=5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(timeout=5)


class Controller(QObject):
    event = Signal(object)

    def __init__(self, app, bridge, runtime, restore=False):
        super().__init__()
        self.app = app
        self.bridge = bridge
        self.runtime = runtime
        self.directory = runtime.directory
        self.restore = restore
        self.config_path = runtime.config_path
        self.config = runtime.config
        self.loop = runtime.loop
        self.conversation_id = None
        self.answer = ""
        self.started = 0.0
        self.first = None
        self.queue_seconds = None
        self.generated_chars = 0
        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(40)
        self.render_timer.timeout.connect(self._render_answer)
        bridge.update_state(status="正在加载历史", busy=True)
        self.event.connect(self._on_event)
        self.ready = asyncio.run_coroutine_threadsafe(self._initialize(), self.loop)
        bridge.send_handler = self.send
        bridge.stopRequested.connect(self.stop)
        bridge.set_settings(self.config["provider"], self.config["model"])
        runtime.settingsChanged.connect(bridge.set_settings)
        bridge.settingsSaved.connect(self.settings)

    async def _initialize(self):
        try:
            await asyncio.wrap_future(self.runtime.ready)
            self.service = self.runtime.service
            store = self.runtime.store
            self.conversation_id = (store.recent_conversation() if self.restore else None) or store.create_conversation()
            messages = store.messages(self.conversation_id)
            history = "\n\n".join(("你" if m["role"] == "user" else "助手") + "：" + m["content"] + (" [图片]" if m.get("image_url") else "") for m in messages)
            self.event.emit(("history", history))
        except Exception as exc:
            self.event.emit(("error", str(exc)))
            raise

    def settings(self, provider, model, key):
        if provider not in {"deepseek", "openai"} or not model.strip():
            self.bridge.update_state(status="请选择服务商并填写模型")
            return
        try:
            if key:
                keyring.set_password("flashUnstander", provider, key)
            self.config.update(provider=provider, model=model.strip())
            self.config_path.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
            self.bridge.set_settings(provider, model.strip())
            self.runtime.settingsChanged.emit(provider, model.strip())
        except Exception as exc:
            QMessageBox.warning(None, "设置失败", str(exc))

    def send(self, question, image_url):
        provider = self.config["provider"]
        try:
            key = keyring.get_password("flashUnstander", provider)
            if not key:
                self.bridge.update_state(status="请先在设置中填写 API Key")
                return False
            images = []
            if image_url:
                path = Path(QUrl(image_url).toLocalFile())
                mime = mimetypes.guess_type(path.name)[0]
                if mime not in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
                    raise ValueError("不支持的图片格式")
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("图片不能超过 10 MB")
                images.append(f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii"))
            self.answer += ("\n\n" if self.answer else "") + "你：" + (question or "请解释这张图片") + (" [图片]" if images else "") + "\n\n助手："
            self.started = time.monotonic()
            self.first = None
            self.queue_seconds = None
            self.generated_chars = 0
            self.bridge.update_state(answer=self.answer, status="排队中", metrics="", busy=True)
            asyncio.run_coroutine_threadsafe(self._submit(question or "请解释这张图片", images, key, dict(self.config)), self.loop)
            return True
        except Exception as exc:
            self.bridge.update_state(status=str(exc), busy=False)
            return False

    async def _submit(self, question, images, key, config):
        client = None
        try:
            await asyncio.wrap_future(self.ready)
            client = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com" if config["provider"] == "deepseek" else None, max_retries=0)
            def factory(messages):
                return stream_response(client, config["provider"], config["model"], messages, config["max_output_tokens"])
            _, future, context = self.service.submit(self.conversation_id, question, factory, count_tokens, image_url=images[0] if images else None, on_event=self.event.emit, model=config["model"], parameters={"provider": config["provider"], "max_output_tokens": config["max_output_tokens"]})
            self.event.emit(("context", f"上下文 {context.turns} 轮，文本约 {context.estimated_tokens} token（不含图片）"))
            await future
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.event.emit(("error", str(exc)))
        finally:
            if client:
                await client.close()

    def stop(self):
        if self.conversation_id:
            self.loop.call_soon_threadsafe(self.service.cancel, self.conversation_id)

    def _on_event(self, event):
        if isinstance(event, tuple):
            if event[0] == "history":
                self.answer = event[1]
                self.bridge.update_state(answer=self.answer, status="就绪", busy=False)
                return
            if event[0] == "context":
                self.bridge.update_state(status=event[1])
                return
            self.bridge.update_state(status=event[1], busy=False)
            return
        elapsed = time.monotonic() - self.started
        if event.kind == "started":
            self.queue_seconds = elapsed
            self.bridge.update_state(status="连接中", metrics=f"排队 {elapsed:.2f}s")
        elif event.kind == "text":
            if self.first is None:
                self.first = elapsed
            self.answer += event.text
            self.generated_chars += len(event.text)
            self.pending_metrics = f"首字 {self.first:.2f}s · {self.generated_chars / max(elapsed, .001):.1f} 字符/s"
            if not self.render_timer.isActive():
                self.render_timer.start()
        elif event.kind == "completed":
            self.render_timer.stop()
            self.bridge.update_state(answer=self.answer, status="完成", busy=False, metrics=f"排队 {self.queue_seconds or 0:.2f}s · 耗时 {elapsed:.2f}s · 输入 {event.input_tokens if event.input_tokens is not None else '未知'} · 输出 {event.output_tokens if event.output_tokens is not None else '未知'}")
        elif event.kind in {"cancelled", "failed"}:
            self.render_timer.stop()
            self.bridge.update_state(answer=self.answer, status="已停止" if event.kind == "cancelled" else "请求失败", busy=False)

    def _render_answer(self):
        self.bridge.update_state(answer=self.answer, status="生成中", metrics=self.pending_metrics)

def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "flashUnstander"
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "application.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "flashUnstander", "程序已运行，请从系统托盘打开窗口。")
        return 1
    try:
        runtime = Runtime(directory)
    except Exception:
        lock.unlock()
        raise
    first = True

    def controller_factory(bridge):
        nonlocal first
        controller = Controller(app, bridge, runtime, restore=first)
        first = False
        return controller

    manager = WindowManager(controller_factory)
    try:
        manager.create_window()
    except Exception:
        try:
            runtime.shutdown()
        finally:
            lock.unlock()
        raise
    try:
        desktop = DesktopIntegration(app)
        desktop.showRequested.connect(manager.show_recent)
        desktop.newWindowRequested.connect(manager.create_window)
        desktop.quitRequested.connect(app.quit)
        bindings = {"Alt+Space": 0x0001, "Ctrl+Alt+Space": 0x0003, "Ctrl+Shift+Space": 0x0006}

        def change_hotkey(value):
            if value not in bindings:
                return
            if value == runtime.config.get("hotkey") and desktop._registered:
                return
            if not desktop.register_hotkey(bindings[value], 0x20):
                for _, _, bridge, _ in manager.windows:
                    bridge.update_state(status="快捷键注册失败，请选择其他组合")
                    bridge.set_hotkey(runtime.config["hotkey"])
                return
            runtime.config["hotkey"] = value
            runtime.config_path.write_text(json.dumps(runtime.config, ensure_ascii=False, indent=2), encoding="utf-8")
            for _, _, bridge, _ in manager.windows:
                bridge.set_hotkey(value)

        def connect_window(window):
            bridge = next(item[2] for item in manager.windows if item[0] is window)
            bridge.set_hotkey(runtime.config["hotkey"])
            bridge.hotkeyRequested.connect(change_hotkey)

        manager.windowCreated.connect(connect_window)
        connect_window(manager.windows[0][0])
        saved_hotkey = runtime.config.get("hotkey", "Alt+Space")
        if saved_hotkey not in bindings:
            saved_hotkey = "Alt+Space"
            runtime.config["hotkey"] = saved_hotkey
        if not desktop.register_hotkey(bindings[saved_hotkey], 0x20):
            manager.windows[0][2].update_state(status="全局快捷键不可用，可通过托盘打开窗口")
        return app.exec()
    finally:
        try:
            if 'desktop' in locals():
                desktop.close()
        finally:
            try:
                runtime.shutdown()
            finally:
                lock.unlock()
