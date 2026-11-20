# flashUnstander

Windows 悬浮窗问答工具。开发环境使用 Python 3.13。

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m flashunstander
```

右键中控球打开设置，选择服务商并输入模型名及 API Key。可调整上下文输入预算、保留轮数和单次输出上限。默认输入预算为 100,000 估算 token，保留最多 20 轮，单次输出上限为 16,384 token。图片未计入本地输入估算。密钥存入 Windows 凭据管理器，会话和图片保存在当前用户的本地应用数据目录中。

启动后可以拖动中控球。每次单击中控球或按 `Alt+Shift+W` 都会开一个窗口，已打开的窗口互不影响。右键菜单可恢复最近窗口或显示全部。问答窗可拖动自绘标题区，也可从边缘或四角缩放。

支持的 DeepSeek 模型可以在窗口内开启思考。在线搜索目前适用于 `deepseek-flash`，开启后由模型决定是否搜索。思考与搜索过程默认折叠，回答支持 Markdown、JSON 和常用 LaTeX 公式。

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
