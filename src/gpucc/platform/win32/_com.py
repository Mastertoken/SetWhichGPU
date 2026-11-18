"""Minimal COM helpers: GUID, LUID and vtable calls via ctypes."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from typing import Any

HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = (("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8))

    @classmethod
    def parse(cls, text: str) -> GUID:
        h = text.replace("-", "").strip("{}")
        return cls(
            int(h[0:8], 16),
            int(h[8:12], 16),
            int(h[12:16], 16),
            (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:])),
        )


class LUID(ctypes.Structure):
    _fields_ = (("LowPart", wt.DWORD), ("HighPart", wt.LONG))

    def as_int(self) -> int:
        return luid_to_int(int(self.LowPart), int(self.HighPart))

    @classmethod
    def from_int(cls, value: int) -> LUID:
        high = (value >> 32) & 0xFFFFFFFF
        if high >= 0x80000000:
            high -= 1 << 32
        return cls(value & 0xFFFFFFFF, high)


def luid_to_int(low: int, high: int) -> int:
    return ((high & 0xFFFFFFFF) << 32) | (low & 0xFFFFFFFF)


def vcall(obj: ctypes.c_void_p, index: int, restype: Any, argtypes: list[Any], *args: Any) -> Any:
    """Call COM vtable method ``index`` on interface pointer ``obj``."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return fn(obj, *args)


def release(obj: ctypes.c_void_p) -> None:
    if obj:
        vcall(obj, 2, wt.ULONG, [])


def hr_failed(hr: int) -> bool:
    return hr < 0
