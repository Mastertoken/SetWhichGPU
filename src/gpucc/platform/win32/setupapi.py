"""SetupAPI: present display-class devices with numeric PCI location and driver info. Read-only."""

from __future__ import annotations

import ctypes
import winreg
from ctypes import wintypes as wt
from dataclasses import dataclass

from gpucc.core.models import PciAddress
from gpucc.platform.win32._com import GUID

GUID_DEVCLASS_DISPLAY = GUID.parse("4d36e968-e325-11ce-bfc1-08002be10318")
_DIGCF_PRESENT = 0x2
_SPDRP_DEVICEDESC = 0x0
_SPDRP_HARDWAREID = 0x1
_SPDRP_DRIVER = 0x9
_SPDRP_FRIENDLYNAME = 0xC
_SPDRP_BUSNUMBER = 0x15
_SPDRP_ADDRESS = 0x1C
_CLASS_ROOT = r"SYSTEM\CurrentControlSet\Control\Class"


class _SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = (
        ("cbSize", wt.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wt.DWORD),
        ("Reserved", ctypes.c_size_t),
    )


_api = ctypes.WinDLL("setupapi", use_last_error=True)
_api.SetupDiGetClassDevsW.restype = wt.HANDLE
_api.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
_api.SetupDiEnumDeviceInfo.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(_SP_DEVINFO_DATA)]
_api.SetupDiGetDeviceRegistryPropertyW.argtypes = [
    wt.HANDLE,
    ctypes.POINTER(_SP_DEVINFO_DATA),
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
    ctypes.c_void_p,
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
]
_api.SetupDiGetDeviceInstanceIdW.argtypes = [
    wt.HANDLE,
    ctypes.POINTER(_SP_DEVINFO_DATA),
    wt.LPWSTR,
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
]
_api.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]


@dataclass(frozen=True, slots=True)
class DisplayDevice:
    instance_id: str
    name: str
    hardware_id: str
    pci: PciAddress | None
    driver_version: str | None

    @property
    def is_pci(self) -> bool:
        return self.instance_id.upper().startswith("PCI\\")


def _string(h: wt.HANDLE, dev: _SP_DEVINFO_DATA, prop: int) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    ok = _api.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(dev), prop, None, buf, ctypes.sizeof(buf), None)
    return buf.value if ok else ""


def _dword(h: wt.HANDLE, dev: _SP_DEVINFO_DATA, prop: int) -> int | None:
    val = wt.DWORD()
    ok = _api.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(dev), prop, None, ctypes.byref(val), 4, None)
    return int(val.value) if ok else None


def _driver_version(driver_key: str) -> str | None:
    if not driver_key:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{_CLASS_ROOT}\\{driver_key}") as k:
            return str(winreg.QueryValueEx(k, "DriverVersion")[0])
    except OSError:
        return None


def display_devices() -> list[DisplayDevice]:
    h = _api.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVCLASS_DISPLAY), None, None, _DIGCF_PRESENT)
    out: list[DisplayDevice] = []
    try:
        i = 0
        while True:
            dev = _SP_DEVINFO_DATA(cbSize=ctypes.sizeof(_SP_DEVINFO_DATA))
            if not _api.SetupDiEnumDeviceInfo(h, i, ctypes.byref(dev)):
                break
            iid = ctypes.create_unicode_buffer(512)
            _api.SetupDiGetDeviceInstanceIdW(h, ctypes.byref(dev), iid, 512, None)
            # Location *text* is localized ("PCI-Bus 3, Gerät 0 …") – use numeric properties.
            bus, addr = _dword(h, dev, _SPDRP_BUSNUMBER), _dword(h, dev, _SPDRP_ADDRESS)
            pci = PciAddress(bus, addr >> 16, addr & 0xFFFF) if bus is not None and addr is not None else None
            out.append(
                DisplayDevice(
                    instance_id=iid.value,
                    name=_string(h, dev, _SPDRP_FRIENDLYNAME) or _string(h, dev, _SPDRP_DEVICEDESC),
                    hardware_id=_string(h, dev, _SPDRP_HARDWAREID),
                    pci=pci,
                    driver_version=_driver_version(_string(h, dev, _SPDRP_DRIVER)),
                )
            )
            i += 1
    finally:
        _api.SetupDiDestroyDeviceInfoList(h)
    return out
