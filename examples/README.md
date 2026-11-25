# 自定义悬浮窗

复制 `src/flashunstander/qml/Main.qml` 后调整布局和颜色。窗口通过上下文属性 `bridge` 读取 `messages`、`status`、`metrics`、`busy`，调用 `send(text, imageUrl)` 和 `stop()`。消息条目提供角色、纯文本、可选的格式化正文、过程文本和状态。

自定义根窗口需要提供 `newWindowRequested()` 信号，以便窗口管理器连接新建操作。可通过 `WindowManager(controller_factory, qml_path=...)` 加载自定义文件。每个窗口由工厂获得独立桥接器和控制器；控制器应连接同一中央会话服务并为新窗口创建独立会话。

官方窗口的 `lightTheme` 属性控制深浅主题，可作为自定义配色的起点。

中控外观与问答窗外观可以分别替换。默认的 `ControlBall` 是一个 Qt 控件，通过 `ControlBridge` 打开最近窗口、新建窗口、显示全部、打开设置和退出。自定义 Qt 控件可以使用同一接口，也可以将桥接对象暴露给自己的 QML。读取 `windowCount` 和 `visibleCount` 获取窗口状态，订阅 `windowsChanged` 后更新显示。启动入口负责创建中控外观，`WindowManager` 负责实例和位置。

## 可运行的经典 Qt 示例

`classic_qt/` 保留星系改版前的圆形悬浮按钮和问答窗口，使用当前的会话服务与模型接口。它使用独立的本地历史和配置目录 `flashUnstander-classic-example`。如果默认程序占用了全局快捷键，可通过经典悬浮按钮新建窗口。

从仓库根目录安装项目后运行：

```powershell
python -m pip install -e .
python examples/classic_qt/main.py
```

`reference/cosmic_agent_widget_270_270_ui.html` 是星系界面的浏览器参考原型，依赖外部 CDN。
