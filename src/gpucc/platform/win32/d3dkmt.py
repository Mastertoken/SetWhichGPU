"""D3DKMT thunks (gdi32): map an adapter LUID to its PCI location. Read-only."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from gpucc.core.models import PciAddress
from gpucc.platform.win32._com import LUID


class _OPENADAPTERFROMLUID(ctypes.Structure):
    _fields_ = (("AdapterLuid", LUID), ("hAdapter", wt.UINT))


class _CLOSEADAPTER(ctypes.Structure):
    _fields_ = (("hAdapter", wt.UINT),)


class _QUERYADAPTERINFO(ctypes.Structure):
    _fields_ = (
        ("hAdapter", wt.UINT),
        ("Type", ctypes.c_int),
        ("pPrivateDriverData", ctypes.c_void_p),
        ("PrivateDriverDataSize", wt.UINT),
    )


class _ADAPTERADDRESS(ctypes.Structure):
    _fields_ = (("BusNumber", wt.UINT), ("DeviceNumber", wt.UINT), ("FunctionNumber", wt.UINT))


_KMTQAITYPE_ADAPTERADDRESS = 6
_INVALID = 0xFFFFFFFF

_gdi32 = ctypes.WinDLL("gdi32")
for _name in ("D3DKMTOpenAdapterFromLuid", "D3DKMTQueryAdapterInfo", "D3DKMTCloseAdapter"):
    getattr(_gdi32, _name).restype = ctypes.c_long


def pci_address_or_none(bus: int, dev: int, fn: int) -> PciAddress | None:
    """Only real PCI locations (bus ≤ 255, device ≤ 31, function ≤ 7). Virtual display adapters
    (e.g. the Microsoft Basic Display Adapter in VMs) report garbage such as device 22048."""
    if _INVALID in (bus, dev, fn) or not (0 <= bus <= 0xFF and 0 <= dev <= 0x1F and 0 <= fn <= 0x7):
        return None
    return PciAddress(bus, dev, fn)


def adapter_pci_address(luid: int) -> PciAddress | None:
    """PCI bus/device/function of the adapter, or ``None`` for virtual/indirect adapters."""
    req = _OPENADAPTERFROMLUID(LUID.from_int(luid), 0)
    if _gdi32.D3DKMTOpenAdapterFromLuid(ctypes.byref(req)) != 0:
        return None
    try:
        addr = _ADAPTERADDRESS()
        q = _QUERYADAPTERINFO(
            req.hAdapter,
            _KMTQAITYPE_ADAPTERADDRESS,
            ctypes.cast(ctypes.byref(addr), ctypes.c_void_p),
            ctypes.sizeof(addr),
        )
        if _gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(q)) != 0:
            return None
        bus, dev, fn = int(addr.BusNumber), int(addr.DeviceNumber), int(addr.FunctionNumber)
        return pci_address_or_none(bus, dev, fn)
    finally:
        _gdi32.D3DKMTCloseAdapter(ctypes.byref(_CLOSEADAPTER(req.hAdapter)))
