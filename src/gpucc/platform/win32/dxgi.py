"""DXGI adapter enumeration (read-only)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt
from dataclasses import dataclass
from enum import IntEnum

from gpucc.core.errors import PlatformApiError
from gpucc.platform.win32._com import GUID, HRESULT, LUID, hr_failed, release, vcall

IID_IDXGIFactory1 = GUID.parse("770aae78-f26f-4dba-a829-253c83d1b387")
IID_IDXGIFactory6 = GUID.parse("c1b6694f-ff09-44a9-b03c-77900a0a1d17")
IID_IDXGIAdapter1 = GUID.parse("29038f61-3839-4626-91fd-086879011a05")
DXGI_ERROR_NOT_FOUND = ctypes.c_long(0x887A0002).value
DXGI_ADAPTER_FLAG_SOFTWARE = 2

_FACTORY1_ENUM_ADAPTERS1 = 12
_FACTORY6_ENUM_BY_PREFERENCE = 29
_ADAPTER1_GET_DESC1 = 10


class GpuPreferenceOrder(IntEnum):
    UNSPECIFIED = 0
    MINIMUM_POWER = 1
    HIGH_PERFORMANCE = 2


class _DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = (
        ("Description", wt.WCHAR * 128),
        ("VendorId", wt.UINT),
        ("DeviceId", wt.UINT),
        ("SubSysId", wt.UINT),
        ("Revision", wt.UINT),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("AdapterLuid", LUID),
        ("Flags", wt.UINT),
    )


@dataclass(frozen=True, slots=True)
class DxgiAdapter:
    description: str
    vendor_id: int
    device_id: int
    subsys_id: int
    revision: int
    dedicated_video_memory: int
    dedicated_system_memory: int
    shared_system_memory: int
    luid: int
    flags: int

    @property
    def is_software(self) -> bool:
        return bool(self.flags & DXGI_ADAPTER_FLAG_SOFTWARE)


_dxgi = ctypes.WinDLL("dxgi")
_dxgi.CreateDXGIFactory1.restype = HRESULT
_dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]


def _describe(adapter: ctypes.c_void_p) -> DxgiAdapter:
    d = _DXGI_ADAPTER_DESC1()
    hr = int(vcall(adapter, _ADAPTER1_GET_DESC1, HRESULT, [ctypes.POINTER(_DXGI_ADAPTER_DESC1)], ctypes.byref(d)))
    if hr_failed(hr):
        raise PlatformApiError("IDXGIAdapter1::GetDesc1", hr)
    return DxgiAdapter(
        description=str(d.Description),
        vendor_id=int(d.VendorId),
        device_id=int(d.DeviceId),
        subsys_id=int(d.SubSysId),
        revision=int(d.Revision),
        dedicated_video_memory=int(d.DedicatedVideoMemory),
        dedicated_system_memory=int(d.DedicatedSystemMemory),
        shared_system_memory=int(d.SharedSystemMemory),
        luid=d.AdapterLuid.as_int(),
        flags=int(d.Flags),
    )


def _factory(iid: GUID) -> ctypes.c_void_p:
    fac = ctypes.c_void_p()
    hr = int(_dxgi.CreateDXGIFactory1(ctypes.byref(iid), ctypes.byref(fac)))
    if hr_failed(hr):
        raise PlatformApiError("CreateDXGIFactory1", hr)
    return fac


def enum_adapters() -> list[DxgiAdapter]:
    """All adapters in DXGI's default order for *this* process."""
    fac = _factory(IID_IDXGIFactory1)
    out: list[DxgiAdapter] = []
    try:
        i = 0
        while True:
            ad = ctypes.c_void_p()
            hr = int(
                vcall(
                    fac,
                    _FACTORY1_ENUM_ADAPTERS1,
                    HRESULT,
                    [wt.UINT, ctypes.POINTER(ctypes.c_void_p)],
                    i,
                    ctypes.byref(ad),
                )
            )
            if hr == DXGI_ERROR_NOT_FOUND:
                break
            if hr_failed(hr):
                raise PlatformApiError("IDXGIFactory1::EnumAdapters1", hr)
            try:
                out.append(_describe(ad))
            finally:
                release(ad)
            i += 1
    finally:
        release(fac)
    return out


_ADAPTER_ENUM_OUTPUTS = 7


def output_counts() -> dict[int, int]:
    """LUID → number of attached outputs (monitors). Used to never disable the display GPU."""
    fac = _factory(IID_IDXGIFactory1)
    out: dict[int, int] = {}
    try:
        i = 0
        while True:
            ad = ctypes.c_void_p()
            hr = int(
                vcall(
                    fac,
                    _FACTORY1_ENUM_ADAPTERS1,
                    HRESULT,
                    [wt.UINT, ctypes.POINTER(ctypes.c_void_p)],
                    i,
                    ctypes.byref(ad),
                )
            )
            if hr == DXGI_ERROR_NOT_FOUND:
                break
            if hr_failed(hr):
                raise PlatformApiError("IDXGIFactory1::EnumAdapters1", hr)
            try:
                count = 0
                while True:
                    output = ctypes.c_void_p()
                    ohr = int(
                        vcall(
                            ad,
                            _ADAPTER_ENUM_OUTPUTS,
                            HRESULT,
                            [wt.UINT, ctypes.POINTER(ctypes.c_void_p)],
                            count,
                            ctypes.byref(output),
                        )
                    )
                    if ohr == DXGI_ERROR_NOT_FOUND or hr_failed(ohr):
                        break
                    release(output)
                    count += 1
                luid = _describe(ad).luid
                out[luid] = out.get(luid, 0) + count
            finally:
                release(ad)
            i += 1
    finally:
        release(fac)
    return out


def adapter_order(preference: GpuPreferenceOrder) -> list[int]:
    """LUIDs in the order DXGI returns them for ``preference`` (IDXGIFactory6)."""
    fac = _factory(IID_IDXGIFactory6)
    out: list[int] = []
    try:
        i = 0
        while True:
            ad = ctypes.c_void_p()
            hr = int(
                vcall(
                    fac,
                    _FACTORY6_ENUM_BY_PREFERENCE,
                    HRESULT,
                    [wt.UINT, ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                    i,
                    int(preference),
                    ctypes.byref(IID_IDXGIAdapter1),
                    ctypes.byref(ad),
                )
            )
            if hr == DXGI_ERROR_NOT_FOUND:
                break
            if hr_failed(hr):
                raise PlatformApiError("IDXGIFactory6::EnumAdapterByGpuPreference", hr)
            try:
                out.append(_describe(ad).luid)
            finally:
                release(ad)
            i += 1
    finally:
        release(fac)
    return out
