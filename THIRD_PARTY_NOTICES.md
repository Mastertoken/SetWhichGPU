# Third-party notices

SetWhichGPU is MIT licensed. It uses the following third-party software at runtime. The installer
(`SetWhichGPU-<version>-setup.exe`) **distributes** these components; their full license texts are
installed to `<install folder>\licenses\` (collected by `tools/release/collect_licenses.py`).

| Component | License | Notes |
|---|---|---|
| [PySide6 / Qt for Python](https://www.qt.io/qt-for-python) (`PySide6-Essentials`, `shiboken6`) | LGPL-3.0-only (or GPL / commercial) | Used unmodified under the LGPL-3.0, as separate dynamically loaded libraries in the `_internal` folder, which you may replace with your own compatible build. Source: [download.qt.io](https://download.qt.io/official_releases/QtForPython/pyside6/), [code.qt.io/pyside](https://code.qt.io/cgit/pyside/pyside-setup.git/) |
| [nvidia-ml-py](https://pypi.org/project/nvidia-ml-py/) | BSD-3-Clause | Python bindings for NVML |
| [Python](https://www.python.org/) | PSF License | Interpreter (embedded in the installer build) |
| [PresentMon](https://github.com/GameTechDev/PresentMon) 2.6.0 (Intel) | MIT | Console build, installed as `tools\PresentMon.exe` for the frame analysis; unmodified official release, SHA-256 pinned |
| [PyInstaller](https://pyinstaller.org/) bootloader | GPL-2.0-or-later with bootloader exception | The exception allows distributing the bundled application under its own license |

The installer itself is built with [Inno Setup](https://jrsoftware.org/isinfo.php) (Inno Setup license, permits use for any purpose).

System libraries that are **used but not distributed** (they come with Windows or the GPU drivers):

| Library | Provided by |
|---|---|
| `nvml.dll` (NVIDIA Management Library) | NVIDIA graphics driver |
| `ControlLib.dll` (Intel Graphics Control Library) | Intel graphics driver – struct layouts follow the public `igcl_api.h` (MIT licensed, intel/drivers.gpu.control-library) |
| `dxgi.dll`, `gdi32.dll` (D3DKMT), `pdh.dll`, `setupapi.dll`, `user32.dll`, `ole32.dll`, … | Windows |

Development-only dependencies (pytest, pytest-qt, ruff, mypy, hatchling) are not shipped.

Trademarks (NVIDIA, Intel, AMD, Steam, Epic Games, GOG, Windows) belong to their respective owners and are used only to describe compatibility.
