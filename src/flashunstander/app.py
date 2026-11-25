"""Desktop entry point and bridge to the asynchronous conversation service."""
import asyncio
import base64
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from functools import lru_cache
from html import escape

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
from .context import select_context
from .control_ball import ControlBall
from .control_bridge import ControlBridge
from .formatting import format_message
from .settings_dialog import (
    DEFAULT_CONTEXT_TOKENS, DEFAULT_CONTEXT_TURNS, DEFAULT_OUTPUT_TOKENS, SettingsDialog,
)

_TOKEN_GROUP = re.compile(r"[A-Za-z0-9_]+|\s+|[^\x00-\x7f]+|[^\w\s]")


@lru_cache(maxsize=1024)
def count_tokens(text):
    # An offline estimate across prose, CJK text and code. Provider usage is authoritative.
    return sum((len(part) + 2) // 3 if part.isascii() else len(part)
               for part in (match[0] for match in _TOKEN_GROUP.finditer(text)))


class Runtime(QObject):
    settingsChanged = Signal(str, str)

    def __init__(self, directory):
        super().__init__()
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.config_path = self.directory / "settings.json"
        self.config = {
            "provider": "deepseek", "model": "deepseek-flash",
            "context_tokens": DEFAULT_CONTEXT_TOKENS, "context_turns": DEFAULT_CONTEXT_TURNS,
            "max_output_tokens": DEFAULT_OUTPUT_TOKENS,
        }
        if self.config_path.exists():
            try:
                saved = json.loads(self.config_path.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    if "context_tokens" not in saved and saved.get("max_output_tokens") == 2048:
                        saved.pop("max_output_tokens")
                    self.config.update({key: saved[key] for key in self.config if key in saved})
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

    def save_settings(self, provider, model, key, tokens, turns, output):
        model = model.strip()
        if provider not in {"deepseek", "openai"} or not model:
            raise ValueError("请选择服务商并填写模型名称")
        if not (1_000 <= tokens <= 100_000 and 0 <= turns <= 200 and 256 <= output <= 32_768):
            raise ValueError("上下文或输出设置超出允许范围")
        updated = dict(self.config, provider=provider, model=model, context_tokens=tokens,
                       context_turns=turns, max_output_tokens=output)
        if key.strip():
            keyring.set_password("flashUnstander", provider, key.strip())
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.config_path)
        self.config.update(updated)
        self.settingsChanged.emit(provider, model)


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


def message_row(role, text, *, status="complete", image=False):
    if image:
        text += " ［图片］"
    return {"role": role, "text": text, "formatted": format_message(text) if role == "assistant" else "",
            "process": "", "status": status}


class Controller(QObject):
    event = Signal(object)

    def __init__(self, app, bridge, runtime, restore=False):
        super().__init__()
        self.app = app
        self.bridge = bridge
        self.runtime = runtime
        self.directory = runtime.directory
        self.restore = restore
        self.config = runtime.config
        self.loop = runtime.loop
        self.conversation_id = None
        self.answer = ""
        self.messages = []
        self.pending_metrics = ""
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
            context = select_context(messages, "", "", count_tokens,
                                     budget=self.config["context_tokens"],
                                     max_turns=self.config["context_turns"])
            self.event.emit(("history", [
                (m["role"], m["content"], m["status"], bool(m.get("image_url"))) for m in messages
            ], context.estimated_tokens))
        except Exception as exc:
            self.event.emit(("error", str(exc)))
            raise

    def settings(self, provider, model, key):
        try:
            self.runtime.save_settings(provider, model, key, self.config["context_tokens"],
                                       self.config["context_turns"], self.config["max_output_tokens"])
        except Exception as exc:
            QMessageBox.warning(None, "设置失败", str(exc))

    def send(self, question, image_url):
        provider = self.config["provider"]
        try:
            key = keyring.get_password("flashUnstander", provider)
            if not key:
                self.bridge.update_state(status="请右键中控球，在设置中填写 API Key")
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
            question = question.strip() or "请解释这张图片"
            self.answer += ("\n\n" if self.answer else "") + "你：" + question + (" [图片]" if images else "") + "\n\n助手："
            self.messages.extend([
                message_row("user", question, image=bool(images)),
                message_row("assistant", "", status="queued"),
            ])
            self.bridge.set_messages(self.messages)
            self.started = time.monotonic()
            self.first = None
            self.queue_seconds = None
            self.generated_chars = 0
            self.pending_metrics = ""
            self.bridge.update_state(answer=self.answer, status="排队中", metrics="", busy=True)
            config = dict(self.config, thinking=self.bridge.thinkingEnabled, search=self.bridge.searchEnabled)
            asyncio.run_coroutine_threadsafe(self._submit(question, images, key, config), self.loop)
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
                return stream_response(client, config["provider"], config["model"], messages,
                                       config["max_output_tokens"], thinking=config["thinking"], search=config["search"])
            parameters = {name: config[name] for name in (
                "provider", "max_output_tokens", "context_tokens", "context_turns", "thinking", "search")}
            _, future, context = self.service.submit(
                self.conversation_id, question, factory, count_tokens,
                budget=config["context_tokens"], max_turns=config["context_turns"],
                image_url=images[0] if images else None, on_event=self.event.emit,
                model=config["model"], parameters=parameters,
            )
            self.event.emit(("context", f"上下文 {context.turns} 轮，文本约 {context.estimated_tokens} token（不含图片）", context.estimated_tokens))
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
                self.bridge.context_tokens = event[2]
                self.messages = [message_row(role, text, status=status, image=image)
                                 for role, text, status, image in event[1]]
                self.bridge.set_messages(self.messages)
                self.answer = "\n\n".join(("你：" if row["role"] == "user" else "助手：") + row["text"]
                                           for row in self.messages)
                self.bridge.update_state(answer=self.answer, status="就绪", busy=False)
                return
            if event[0] == "context":
                self.bridge.context_tokens = event[2]
                self.bridge.update_state(status=event[1])
                return
            if self.messages and self.messages[-1]["status"] in {"queued", "streaming"}:
                self._finish_message("failed")
            self.bridge.update_state(status=event[1], busy=False)
            return
        elapsed = time.monotonic() - self.started
        if event.kind == "started":
            self.messages[-1]["status"] = "streaming"
            self.queue_seconds = elapsed
            self.bridge.update_state(status="连接中", metrics=f"排队 {elapsed:.2f}s")
        elif event.kind == "text":
            if self.first is None:
                self.first = elapsed
            self.answer += event.text
            self.messages[-1]["text"] += event.text
            self.generated_chars += len(event.text)
            self.pending_metrics = f"首字 {self.first:.2f}s · {self.generated_chars / max(elapsed, .001):.1f} 字符/s"
            if not self.render_timer.isActive():
                self.render_timer.start()
        elif event.kind in {"reasoning", "search"}:
            row = self.messages[-1]
            row["process"] += event.text
            if not self.render_timer.isActive():
                self.render_timer.start()
        elif event.kind in {"completed", "truncated"}:
            completed = event.kind == "completed"
            self._finish_message("complete" if completed else "truncated")
            status = "完成" if completed else "回答达到长度限制"
            self.bridge.update_state(answer=self.answer, status=status, busy=False, metrics=f"排队 {self.queue_seconds or 0:.2f}s · 耗时 {elapsed:.2f}s · 输入 {event.input_tokens if event.input_tokens is not None else '未知'} · 输出 {event.output_tokens if event.output_tokens is not None else '未知'}")
        elif event.kind in {"cancelled", "failed"}:
            self._finish_message(event.kind)
            self.bridge.update_state(answer=self.answer, status="已停止" if event.kind == "cancelled" else "请求失败", busy=False)

    def _render_answer(self):
        row = self.messages[-1]
        row["formatted"] = escape(row["text"]).replace("\n", "<br>")
        self.bridge.set_messages(self.messages)
        self.bridge.update_state(answer=self.answer, status="生成中", metrics=self.pending_metrics)

    def _finish_message(self, status):
        self.render_timer.stop()
        row = self.messages[-1]
        row["status"] = status
        row["formatted"] = format_message(row["text"])
        self.bridge.set_messages(self.messages)

def main(*, launcher_class=ControlBall, qml_path=None, data_name="flashUnstander"):
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / data_name
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

    manager = WindowManager(controller_factory, qml_path=qml_path)
    try:
        desktop = DesktopIntegration(app)
        controls = ControlBridge(manager, app.quit, lambda: SettingsDialog(runtime).exec())
        desktop.hotkeyRequested.connect(controls.openNew)
        desktop.showRequested.connect(controls.showAll)
        desktop.quitRequested.connect(controls.quit)
        ball = launcher_class(app, controls, shortcut_available=desktop.register_hotkey())
        ball.show()
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
