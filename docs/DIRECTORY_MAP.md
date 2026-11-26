# 目录地图

| 位置 | 内容 |
| --- | --- |
| `src/flashunstander/` | 应用入口、会话、模型接口、Windows 托盘和全局热键。 |
| `src/flashunstander/qml/` | Qt Quick 问答窗口、GPU 星系场景和球体着色器。 |
| `tests/` | 自动化测试，覆盖会话、渲染、纹理缓存等行为。 |
| `tests/windows/` | Windows 原生窗口、全局热键和正常退出的验证脚本。 |
| `examples/classic_qt/` | 可独立运行的经典 Qt 界面开发示例。 |
| `examples/reference/` | 星系界面的 HTML 参考原型。 |
| `packaging/` | Windows 锁定依赖、PyInstaller 配置、入口和可选的 Inno Setup 配置。 |
| `scripts/build-windows.ps1` | 构建入口。中间文件写入 `build/pyinstaller/`，成功后把 EXE 放到根目录。 |
| `docs/screenshots/` | README 使用的项目截图。 |

星系布局和交互在 `control_ball.py`。`orbit.py` 计算轨道，`closeup.py` 计算近景摄影机，`gpu_spheres.py` 连接 Qt Quick 场景。纹理生成和缓存分别位于 `cosmic.py`、`earth_material.py`、`ring_material.py` 和 `texture_cache.py`。

修改球体着色器 `sphere.frag` 后，在仓库根目录用同一套 Qt 工具更新运行时使用的 `sphere.frag.qsb`。

```powershell
.\.venv\Lib\site-packages\PySide6\qsb.exe --glsl "100 es,120,150" --hlsl 50 --msl 12 -o src/flashunstander/qml/sphere.frag.qsb src/flashunstander/qml/sphere.frag
```

Windows 验证脚本在桌面会话内运行。

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe tests/windows/desktop_smoke.py
.\.venv\Scripts\python.exe tests/windows/exit_smoke.py
```

本地依赖、构建目录和根目录 EXE 由 Git 忽略。模型设置与历史使用 `%LOCALAPPDATA%\flashUnstander`，凭据使用 Windows 凭据管理器。
