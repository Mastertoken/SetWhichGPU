# Third-party notices

SetWhichGPU is MIT licensed. It uses the following third-party software at runtime:

| Component | License | Notes |
|---|---|---|
| [PySide6 / Qt for Python](https://www.qt.io/qt-for-python) (`PySide6-Essentials`, `shiboken6`) | LGPL-3.0-only (or commercial) | Used unmodified as a dynamically loaded library. Distributed builds must keep PySide6 replaceable and ship its license text |
| [nvidia-ml-py](https://pypi.org/project/nvidia-ml-py/) | BSD-3-Clause | Python bindings for NVML |
| [Python](https://www.python.org/) | PSF License | Interpreter |

System libraries that are **used but not distributed** (they come with Windows or the GPU drivers):

| Library | Provided by |
|---|---|
| `nvml.dll` (NVIDIA Management Library) | NVIDIA graphics driver |
| `ControlLib.dll` (Intel Graphics Control Library) | Intel graphics driver – struct layouts follow the public `igcl_api.h` (MIT licensed, intel/drivers.gpu.control-library) |
| `dxgi.dll`, `gdi32.dll` (D3DKMT), `pdh.dll`, `setupapi.dll`, `user32.dll`, `ole32.dll`, … | Windows |

Development-only dependencies (pytest, pytest-qt, ruff, mypy, hatchling) are not shipped.

Trademarks (NVIDIA, Intel, AMD, Steam, Epic Games, GOG, Windows) belong to their respective owners and are used only to describe compatibility.
