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
- `src/flashunstander/window_bridge.py`、`qml/Main.qml`：单窗口接口及界面初稿。
- `tests/test_storage_context.py`：持久化、分页及上下文预算测试。
- `tests/test_scheduler.py`：并发、排队、取消及会话排他测试。
- `tests/test_mock_stream.py`：模拟流测试。
- `tests/test_provider.py`、`tests/test_service.py`：供应商适配及会话服务测试。
- `docs/PROGRESS.md`：阶段进度、设计决定和测试授权记录。
- `.venv/`：本地虚拟环境，不提交。
- `.scratch/`、`build/`、`dist/`：临时文件及构建产物，不提交。

后续按需加入 `examples/`、`scripts/` 和 `packaging/`。运行数据和凭据不存放于项目目录。
