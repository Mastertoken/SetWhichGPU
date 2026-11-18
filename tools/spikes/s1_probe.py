"""Spike S1 probe: print which adapter DXGI hands this process by default.

Runs inside a renamed copy of python.exe so it gets its own entry in
HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences. Read-only.
"""

from __future__ import annotations

import ctypes
import json
import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s2_adapters import (  # noqa: E402
    DXGI_ERROR_NOT_FOUND,
    HRESULT,
    IDXGIFactory1_EnumAdapters1,
    IID_IDXGIFactory1,
    _desc,
    dxgi,
    release,
    vcall,
)

KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"


def default_adapter() -> str:
    fac = ctypes.c_void_p()
    hr = dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory1), ctypes.byref(fac))
    if hr < 0:
        raise OSError(hr)
    try:
        ad = ctypes.c_void_p()
        hr = vcall(fac, IDXGIFactory1_EnumAdapters1, HRESULT, [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)], 0, ctypes.byref(ad))
        if hr == DXGI_ERROR_NOT_FOUND:
            return "<none>"
        d = _desc(ad)
        release(ad)
        return f"{d['description']} ({d['vendor_id']}:{d['device_id']})"
    finally:
        release(fac)


def main() -> int:
    exe = sys.executable
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            pref, _ = winreg.QueryValueEx(k, exe)
    except OSError:
        pref = None
    print(json.dumps({"exe": exe, "registry_value": pref, "dxgi_default_adapter": default_adapter()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
