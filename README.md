# flashUnstander

Windows 悬浮窗问答工具。开发环境使用 Python 3.13。

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m flashunstander
```

首次打开设置，选择服务商并输入模型名及 API Key。密钥存入 Windows 凭据管理器，会话和图片保存在当前用户的本地应用数据目录中。图片输入能力取决于所选模型。上下文的文本 token 数为保守估算，图片未计入估算。

启动后可以拖动中控球。单击中控球或按 `Alt+Shift+W` 打开最近的问答窗，点「＋」新建问答窗。问答窗可拖动自绘标题区，亦可从边缘或四角缩放。

Windows 构建使用 Python 3.13 x64。新建虚拟环境时，可从 `packaging/requirements-windows.txt` 安装固定版本的依赖。

```powershell
.\.venv\Scripts\python.exe -m pip install -r packaging\requirements-windows.txt
.\scripts\build-windows.ps1
```

目录版入口为 `dist/flashUnstander/flashUnstander.exe`，应随同其所在目录一起分发。安装 Inno Setup 后，可用以下命令同时生成 `dist/installer/` 下的安装包。将示例路径替换为实际的编译器路径。

```powershell
.\scripts\build-windows.ps1 -InnoCompiler "C:\Program Files\Inno Setup 7\ISCC.exe"
```

安装包按当前 Windows 用户安装。卸载后保留本地会话和凭据，便于重新安装后继续使用。
