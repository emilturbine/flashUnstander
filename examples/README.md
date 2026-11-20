# 自定义悬浮窗

复制 `src/flashunstander/qml/Main.qml` 后调整布局和颜色。窗口通过上下文属性 `bridge` 读取 `messages`、`status`、`metrics`、`busy`，调用 `send(text, imageUrl)` 和 `stop()`。消息条目提供角色、纯文本、可选的格式化正文、过程文本和状态。

自定义根窗口需要提供 `newWindowRequested()` 信号，以便窗口管理器连接新建操作。可通过 `WindowManager(controller_factory, qml_path=...)` 加载自定义文件。每个窗口由工厂获得独立桥接器和控制器；控制器应连接同一中央会话服务并为新窗口创建独立会话。

官方窗口的 `lightTheme` 属性控制深浅主题，可作为自定义配色的起点。

中控外观与问答窗外观可以分别替换。默认的 `ControlBall` 是一个 Qt 控件，通过 `ControlBridge` 打开最近窗口、新建窗口、显示全部、打开设置和退出。自定义 Qt 控件可以使用同一接口，也可以将桥接对象暴露给自己的 QML。读取 `windowCount` 和 `visibleCount` 获取窗口状态，订阅 `windowsChanged` 后更新显示。启动入口负责创建中控外观，`WindowManager` 负责实例和位置。
