# 目录地图

- `pyproject.toml`：依赖、构建及测试配置。
- `README.md`：开发版启动和配置说明。
- `src/flashunstander/app.py`、`__main__.py`：应用入口、后台线程和窗口控制器。
- `src/flashunstander/storage.py`：SQLite 会话、消息及分页。
- `src/flashunstander/context.py`：完整问答轮次筛选和输入预算。
- `src/flashunstander/scheduler.py`：异步 FIFO 调度及取消。
- `src/flashunstander/mock_stream.py`：测试用模拟流事件。
- `src/flashunstander/provider.py`：OpenAI 和 DeepSeek 流式接口适配。
- `src/flashunstander/service.py`：会话、存储和调度协调。
- `src/flashunstander/desktop.py`：Windows 全局热键及托盘。
- `src/flashunstander/control_bridge.py`：中控操作及窗口可见状态接口。
- `src/flashunstander/control_ball.py`：默认中控球外观及圆形点击范围。
- `src/flashunstander/settings_dialog.py`：中控设置表单和上下文默认值。
- `src/flashunstander/formatting.py`：离线 Markdown、JSON 和基础 LaTeX 渲染。
- `src/flashunstander/window_manager.py`：窗口实例与控制器绑定。
- `src/flashunstander/window_bridge.py`、`qml/Main.qml`：单窗口接口及界面初稿。
- `tests/test_storage_context.py`：持久化、分页及上下文预算测试。
- `tests/test_scheduler.py`：并发、排队、取消及会话排他测试。
- `tests/test_mock_stream.py`：模拟流测试。
- `tests/test_provider.py`、`tests/test_service.py`：供应商适配及会话服务测试。
- `tests/test_formatting.py`：消息格式转换及外部资源过滤。
- `tests/desktop_smoke.py`：单独运行的 Windows 可见窗口、模拟并发及热键冲突验证。
- `tests/exit_smoke.py`：验证正常退出释放实例锁和 SQLite 文件句柄。
- `examples/README.md`：自定义窗口接口示例说明。
- `docs/PROGRESS.md`：阶段进度、设计决定和测试授权记录。
- `scripts/build-windows.ps1`：根目录单文件 EXE 和可选安装包的构建入口。
- `packaging/`：冻结程序入口、PyInstaller 配置、Inno Setup 脚本和 Windows 依赖清单。
- `.venv/`：本地虚拟环境，不提交。
- `.scratch/`、`build/`、`dist/`：临时文件及构建产物，不提交。

运行数据和凭据不存放于项目目录。

- `examples/classic_qt/`：可独立启动的经典 Qt 开发示例。
- `examples/reference/`：星系界面的 HTML 参考原型。
