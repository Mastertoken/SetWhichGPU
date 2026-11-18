"""Performance Data Helper (PDH) wrapper. Uses English counter paths (locale independent)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

from gpucc.core.errors import PlatformApiError

PDH_MORE_DATA = 0x800007D2
PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
_PDH_CSTATUS_VALID = 0
_PDH_CSTATUS_NEW_DATA = 1


class _FMT_COUNTERVALUE(ctypes.Structure):
    _fields_ = (("CStatus", wt.DWORD), ("doubleValue", ctypes.c_double))


class _FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
    _fields_ = (("szName", wt.LPWSTR), ("FmtValue", _FMT_COUNTERVALUE))


_pdh = ctypes.WinDLL("pdh")
_pdh.PdhOpenQueryW.argtypes = [wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
_pdh.PdhAddEnglishCounterW.argtypes = [wt.HANDLE, wt.LPCWSTR, ctypes.c_size_t, ctypes.POINTER(wt.HANDLE)]
_pdh.PdhCollectQueryData.argtypes = [wt.HANDLE]
_pdh.PdhCloseQuery.argtypes = [wt.HANDLE]
_pdh.PdhGetFormattedCounterArrayW.argtypes = [
    wt.HANDLE,
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(wt.DWORD),
    ctypes.c_void_p,
]
for _n in (
    "PdhOpenQueryW",
    "PdhAddEnglishCounterW",
    "PdhCollectQueryData",
    "PdhGetFormattedCounterArrayW",
    "PdhCloseQuery",
):
    getattr(_pdh, _n).restype = wt.DWORD


class PdhQuery:
    def __init__(self) -> None:
        self._h = wt.HANDLE()
        rc = int(_pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._h)))
        if rc:
            raise PlatformApiError("PdhOpenQueryW", rc)
        self._closed = False

    def add(self, path: str) -> wt.HANDLE:
        counter = wt.HANDLE()
        rc = int(_pdh.PdhAddEnglishCounterW(self._h, path, 0, ctypes.byref(counter)))
        if rc:
            raise PlatformApiError("PdhAddEnglishCounterW", rc, path)
        return counter

    def collect(self) -> None:
        rc = int(_pdh.PdhCollectQueryData(self._h))
        if rc:
            raise PlatformApiError("PdhCollectQueryData", rc)

    @staticmethod
    def read(counter: wt.HANDLE, fmt: int = PDH_FMT_DOUBLE) -> dict[str, float]:
        """Instance name → value. Duplicate instance names are summed."""
        size, count = wt.DWORD(0), wt.DWORD(0)
        rc = int(_pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), None))
        if rc != PDH_MORE_DATA:
            if rc:
                raise PlatformApiError("PdhGetFormattedCounterArrayW", rc)
            return {}
        buf = ctypes.create_string_buffer(size.value)
        rc = int(_pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), buf))
        if rc:
            raise PlatformApiError("PdhGetFormattedCounterArrayW", rc)
        items = ctypes.cast(buf, ctypes.POINTER(_FMT_COUNTERVALUE_ITEM_W))
        out: dict[str, float] = {}
        for i in range(count.value):
            item = items[i]
            if int(item.FmtValue.CStatus) in (_PDH_CSTATUS_VALID, _PDH_CSTATUS_NEW_DATA):
                name = str(item.szName)
                out[name] = out.get(name, 0.0) + float(item.FmtValue.doubleValue)
        return out

    def close(self) -> None:
        if not self._closed:
            _pdh.PdhCloseQuery(self._h)
            self._closed = True
