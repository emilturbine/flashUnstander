from pathlib import Path
import sys
from importlib.util import find_spec

packaging = Path(SPECPATH)
source = packaging.parent / "src"
qml = source / "flashunstander" / "qml"
conda_libraries = Path(sys.base_prefix) / "Library" / "bin"
# A venv backed by Conda has no conda-meta, so PyInstaller may miss these DLLs.
runtime_binaries = [
    (str(path), ".")
    for name in ("ffi.dll", "libmpdec-4.dll", "sqlite3.dll")
    if (path := conda_libraries / name).is_file()
]

analysis = Analysis(
    [str(packaging / "launcher.py")],
    pathex=[str(source)],
    binaries=runtime_binaries,
    datas=[(str(qml / name), "flashunstander/qml") for name in (
        "Main.qml", "GpuSphereScene.qml", "sphere.frag.qsb",
    )],
    hiddenimports=["PySide6.QtQuick", "keyring.backends.Windows"],
)
archive = PYZ(analysis.pure)
# Python's base environment and Qt can ship different MSVC runtime builds.
# Windows reuses already-loaded DLLs by basename, so use Qt's copy at the
# bundle root as well as in PySide6 before a Python extension loads it.
qt_directory = Path(find_spec("PySide6").origin).parent
qt_runtime = {
    dll.name.lower(): dll
    for pattern in ("msvcp140*.dll", "vcruntime140*.dll")
    for dll in qt_directory.glob(pattern)
}
runtime = [
    (destination, str(qt_runtime.get(destination.lower(), original)), kind)
    for destination, original, kind in analysis.binaries
]
root_destinations = {destination.lower() for destination, _, _ in runtime}
runtime.extend(
    (name, str(dll), "BINARY")
    for name, dll in qt_runtime.items()
    if name not in root_destinations
)
program = EXE(
    archive,
    analysis.scripts,
    runtime,
    analysis.datas,
    name="flashUnstander",
    console=False,
    upx=False,
)
