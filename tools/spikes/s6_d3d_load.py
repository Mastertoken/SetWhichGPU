"""Spike S6 helper: create a D3D11 device on the *default* adapter (honours the per-app
GPU preference), allocate a GPU buffer and hold it for N seconds. Prints PID + adapter.

Run inside build/probe/gpucc-dxgi-probe.exe. Creates no files, writes nothing.
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from s1_probe import default_adapter  # noqa: E402
from s2_adapters import HRESULT, release, vcall  # noqa: E402


class D3D11_BUFFER_DESC(ctypes.Structure):
    _fields_ = [("ByteWidth", wt.UINT), ("Usage", ctypes.c_int), ("BindFlags", wt.UINT), ("CPUAccessFlags", wt.UINT), ("MiscFlags", wt.UINT), ("StructureByteStride", wt.UINT)]


def main() -> int:
    hold_s = float(sys.argv[1]) if len(sys.argv) > 1 else 8.0
    mib = int(sys.argv[2]) if len(sys.argv) > 2 else 256
    d3d11 = ctypes.WinDLL("d3d11")
    d3d11.D3D11CreateDevice.restype = HRESULT
    dev, ctx, fl = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_int()
    # pAdapter=NULL + DRIVER_TYPE_HARDWARE(1) -> default adapter chosen by Windows
    hr = d3d11.D3D11CreateDevice(None, 1, None, 0, None, 0, 7, ctypes.byref(dev), ctypes.byref(fl), ctypes.byref(ctx))
    if hr < 0:
        print(json.dumps({"error": f"D3D11CreateDevice 0x{hr & 0xFFFFFFFF:08X}"}))
        return 1
    buffers = []
    for _ in range(mib // 64):  # several 64 MiB buffers, DEFAULT usage, UAV bind
        desc = D3D11_BUFFER_DESC(64 * 2**20, 0, 0x80, 0, 0, 0)
        buf = ctypes.c_void_p()
        hr = vcall(dev, 3, HRESULT, [ctypes.POINTER(D3D11_BUFFER_DESC), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(desc), None, ctypes.byref(buf))
        if hr >= 0:
            buffers.append(buf)
    print(json.dumps({"pid": __import__("os").getpid(), "dxgi_default_adapter": default_adapter(), "buffers_mib": len(buffers) * 64}), flush=True)
    time.sleep(hold_s)
    for b in buffers:
        release(b)
    release(ctx)
    release(dev)
    return 0


if __name__ == "__main__":
    sys.exit(main())
