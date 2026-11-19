# 自定义悬浮窗

复制 `src/flashunstander/qml/Main.qml` 后调整布局和颜色。窗口通过上下文属性 `bridge` 读取 `answer`、`status`、`metrics`、`busy`，调用 `send(text, imageUrl)` 和 `stop()`，并使用 `saveSettings(provider, model, key)` 保存设置。

自定义根窗口需要提供 `newWindowRequested()` 信号，以便窗口管理器连接新建操作。可通过 `WindowManager(controller_factory, qml_path=...)` 加载自定义文件。每个窗口由工厂获得独立桥接器和控制器；控制器应连接同一中央会话服务并为新窗口创建独立会话。

官方窗口的 `lightTheme` 属性控制深浅主题，可作为自定义配色的起点。
