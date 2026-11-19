# flashUnstander

Windows 悬浮窗问答工具。开发环境使用 Python 3.13。

```powershell
.\.venv\Scripts\python.exe -m flashunstander
```

首次打开设置，选择服务商并输入模型名及 API Key。密钥存入 Windows 凭据管理器，会话和图片保存在当前用户的本地应用数据目录中。图片输入能力取决于所选模型。上下文的文本 token 数为保守估算，图片未计入估算。

当前为第二阶段开发版本，尚未完成该阶段测试及发布打包。
