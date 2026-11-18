# PyInstaller spec for SetWhichGPU – build with tools/release/build_installer.ps1.
# One-folder build on purpose: starts faster than one-file, triggers fewer antivirus false positives,
# and keeps the Qt DLLs as separate, replaceable files (LGPL).
# ruff: noqa
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "gpucc" / "__init__.py").read_text()).group(1)
NUMS = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMS, prodvers=NUMS),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", "SetWhichGPU contributors"),
                        StringStruct("FileDescription", "SetWhichGPU"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "SetWhichGPU"),
                        StringStruct("LegalCopyright", "MIT License – SetWhichGPU contributors"),
                        StringStruct("OriginalFilename", "SetWhichGPU.exe"),
                        StringStruct("ProductName", "SetWhichGPU"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    datas=[(str(SRC / "gpucc" / "assets"), "gpucc/assets")],
    hiddenimports=[
        # imported lazily inside functions
        "gpucc.gamemode.helper",
        "gpucc.uninstall",
        "gpucc.monitoring.sources.nvml",
        "gpucc.monitoring.sources.igcl",
        "gpucc.monitoring.sources.pdh",
        "pynvml",
    ],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "ssl",
        "_ssl",
        "PySide6.QtNetwork",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtSvg",
    ],
    noarchive=False,
)

# Not needed by a Qt Widgets tray app that makes no network connections and loads only PNG/ICO:
DROP = (
    "opengl32sw.dll",  # software OpenGL fallback (~20 MB)
    "libcrypto-",  # OpenSSL – no network access
    "libssl-",
    "qt6network",
    "qt6svg",
    "qt6pdf",
    "qt6qml",
    "qt6quick",
    "qt6opengl",
    "/translations/",  # Qt's own translations are never loaded
    "/qdirect2d.dll",
    "/qminimal.dll",
    "/qoffscreen.dll",
    "/qtiff.dll",
    "/qjpeg.dll",
    "/qwebp.dll",
    "/qgif.dll",
    "/qicns.dll",
    "/qsvg.dll",
    "/qpdf.dll",
    "/qtga.dll",
    "/qwbmp.dll",
    "/qsvgicon.dll",
    "/qnetworklistmanager.dll",
    "/qschannelbackend.dll",
    "/qcertonlybackend.dll",
    "/qopensslbackend.dll",
)


def _keep(entry):
    dest = entry[0].replace("\\", "/").lower()
    return not any(d in "/" + dest for d in DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SetWhichGPU",
    icon=str(SRC / "gpucc" / "assets" / "icon.ico"),
    version=version_info,
    console=False,  # tray app – no console window
    upx=False,  # UPX-packed executables are flagged by antivirus far more often
    disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SetWhichGPU", upx=False)
