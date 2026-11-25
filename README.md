# flashUnstander

Windows 桌面星系问答工具。每颗行星对应一个会话，大小随文本上下文用量变化。重启后，非空会话会保留为行星。

## 使用

1. 双击根目录的 `flashUnstander.exe` 启动。单文件版可直接分发，无需安装 Python。
2. 右键恒星，打开「设置」，配置服务商、模型名和 API Key。
3. 点击恒星或按 `Alt+Shift+W` 新建问答。点击行星恢复会话，滚轮切换选中行星。右键行星可删除对应会话。
4. 在「星系外观设置」中调节尺寸、亮度、阴影补光，以及轨道线宽和颜色。

会话保存在当前用户的本地应用数据目录。API Key 存在 Windows 凭据管理器。

## 截图

![待机状态下的桌面星系](docs/screenshots/standby.png)

![星系展开与问答窗口](docs/screenshots/conversation.png)

## 从源码启动与构建

使用 Python 3.13 x64。安装依赖后可双击 `启动.cmd` 运行源码，或构建根目录的单文件 EXE。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r packaging\requirements-windows.txt
.\scripts\build-windows.ps1
```
