"""Spike S2: enumerate GPUs via DXGI + D3DKMT (ctypes) and match with SetupAPI and NVML.

Read-only. Prints JSON. Usage:  uv run python tools/spikes/s2_adapters.py
"""

from __future__ import annotations

import ctypes
import json
import re
import sys
from ctypes import wintypes as wt
from typing import Any

# ---------------------------------------------------------------- COM basics
HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, s: str) -> GUID:
        h = s.replace("-", "")
        return cls(
            int(h[0:8], 16),
            int(h[8:12], 16),
            int(h[12:16], 16),
            (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:])),
        )


IID_IDXGIFactory1 = GUID.parse("770aae78-f26f-4dba-a829-253c83d1b387")
IID_IDXGIFactory6 = GUID.parse("c1b6694f-ff09-44a9-b03c-77900a0a1d17")
IID_IDXGIAdapter1 = GUID.parse("29038f61-3839-4626-91fd-086879011a05")
DXGI_ERROR_NOT_FOUND = ctypes.c_long(0x887A0002).value


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]

    def as_int(self) -> int:
        return (self.HighPart << 32) | self.LowPart


class DXGI_ADAPTER_DESC1(ctypes.Structure):
    _fields_ = [
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
    ]


def vcall(obj: ctypes.c_void_p, index: int, restype: Any, argtypes: list[Any], *args: Any) -> Any:
    """Call COM vtable method `index` on interface pointer `obj`."""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[index])
    return fn(obj, *args)


def release(obj: ctypes.c_void_p) -> None:
    vcall(obj, 2, wt.ULONG, [])


# vtable indices
IDXGIFactory1_EnumAdapters1 = 12
IDXGIFactory6_EnumAdapterByGpuPreference = 29
IDXGIAdapter1_GetDesc1 = 10

dxgi = ctypes.WinDLL("dxgi")
dxgi.CreateDXGIFactory1.restype = HRESULT
dxgi.CreateDXGIFactory1.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]


def _desc(adapter: ctypes.c_void_p) -> dict[str, Any]:
    d = DXGI_ADAPTER_DESC1()
    hr = vcall(adapter, IDXGIAdapter1_GetDesc1, HRESULT, [ctypes.POINTER(DXGI_ADAPTER_DESC1)], ctypes.byref(d))
    if hr < 0:
        raise OSError(f"GetDesc1 failed 0x{hr & 0xFFFFFFFF:08X}")
    return {
        "description": d.Description,
        "vendor_id": f"{d.VendorId:04X}",
        "device_id": f"{d.DeviceId:04X}",
        "subsys_id": f"{d.SubSysId:08X}",
        "revision": f"{d.Revision:02X}",
        "dedicated_vram_mib": d.DedicatedVideoMemory // 2**20,
        "dedicated_sys_mib": d.DedicatedSystemMemory // 2**20,
        "shared_sys_mib": d.SharedSystemMemory // 2**20,
        "luid": f"0x{d.AdapterLuid.HighPart & 0xFFFFFFFF:08X}_0x{d.AdapterLuid.LowPart:08X}",
        "_luid": (d.AdapterLuid.LowPart, d.AdapterLuid.HighPart),
        "software": bool(d.Flags & 2),
    }


def dxgi_adapters() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    fac = ctypes.c_void_p()
    hr = dxgi.CreateDXGIFactory1(ctypes.byref(IID_IDXGIFactory6), ctypes.byref(fac))
    if hr < 0:
        raise OSError(f"CreateDXGIFactory1(IDXGIFactory6) failed 0x{hr & 0xFFFFFFFF:08X}")
    try:
        adapters: list[dict[str, Any]] = []
        i = 0
        while True:
            ad = ctypes.c_void_p()
            hr = vcall(fac, IDXGIFactory1_EnumAdapters1, HRESULT, [wt.UINT, ctypes.POINTER(ctypes.c_void_p)], i, ctypes.byref(ad))
            if hr == DXGI_ERROR_NOT_FOUND:
                break
            if hr < 0:
                raise OSError(f"EnumAdapters1 failed 0x{hr & 0xFFFFFFFF:08X}")
            adapters.append(_desc(ad))
            release(ad)
            i += 1
        orders: dict[str, list[str]] = {}
        for name, pref in (("unspecified", 0), ("minimum_power", 1), ("high_performance", 2)):
            order: list[str] = []
            j = 0
            while True:
                ad = ctypes.c_void_p()
                hr = vcall(
                    fac,
                    IDXGIFactory6_EnumAdapterByGpuPreference,
                    HRESULT,
                    [wt.UINT, ctypes.c_int, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                    j,
                    pref,
                    ctypes.byref(IID_IDXGIAdapter1),
                    ctypes.byref(ad),
                )
                if hr == DXGI_ERROR_NOT_FOUND:
                    break
                if hr < 0:
                    raise OSError(f"EnumAdapterByGpuPreference failed 0x{hr & 0xFFFFFFFF:08X}")
                order.append(_desc(ad)["description"])
                release(ad)
                j += 1
            orders[name] = order
        return adapters, orders
    finally:
        release(fac)


# ---------------------------------------------------------------- D3DKMT
class D3DKMT_OPENADAPTERFROMLUID(ctypes.Structure):
    _fields_ = [("AdapterLuid", LUID), ("hAdapter", wt.UINT)]


class D3DKMT_CLOSEADAPTER(ctypes.Structure):
    _fields_ = [("hAdapter", wt.UINT)]


class D3DKMT_QUERYADAPTERINFO(ctypes.Structure):
    _fields_ = [("hAdapter", wt.UINT), ("Type", ctypes.c_int), ("pPrivateDriverData", ctypes.c_void_p), ("PrivateDriverDataSize", wt.UINT)]


class D3DKMT_ADAPTERADDRESS(ctypes.Structure):
    _fields_ = [("BusNumber", wt.UINT), ("DeviceNumber", wt.UINT), ("FunctionNumber", wt.UINT)]


class D3DKMT_ADAPTERREGISTRYINFO(ctypes.Structure):
    _fields_ = [("AdapterString", wt.WCHAR * 260), ("BiosString", wt.WCHAR * 260), ("DacType", wt.WCHAR * 260), ("ChipType", wt.WCHAR * 260)]


KMTQAITYPE_ADAPTERADDRESS = 6
KMTQAITYPE_ADAPTERREGISTRYINFO = 8

gdi32 = ctypes.WinDLL("gdi32")
for _n in ("D3DKMTOpenAdapterFromLuid", "D3DKMTQueryAdapterInfo", "D3DKMTCloseAdapter"):
    getattr(gdi32, _n).restype = ctypes.c_long


def kmt_info(luid: tuple[int, int]) -> dict[str, Any]:
    o = D3DKMT_OPENADAPTERFROMLUID(LUID(*luid), 0)
    st = gdi32.D3DKMTOpenAdapterFromLuid(ctypes.byref(o))
    if st != 0:
        return {"error": f"OpenAdapterFromLuid NTSTATUS 0x{st & 0xFFFFFFFF:08X}"}
    try:
        out: dict[str, Any] = {}
        addr = D3DKMT_ADAPTERADDRESS()
        q = D3DKMT_QUERYADAPTERINFO(o.hAdapter, KMTQAITYPE_ADAPTERADDRESS, ctypes.cast(ctypes.byref(addr), ctypes.c_void_p), ctypes.sizeof(addr))
        st = gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(q))
        out["pci_address"] = f"{addr.BusNumber:02X}:{addr.DeviceNumber:02X}.{addr.FunctionNumber}" if st == 0 else f"NTSTATUS 0x{st & 0xFFFFFFFF:08X}"
        reg = D3DKMT_ADAPTERREGISTRYINFO()
        q = D3DKMT_QUERYADAPTERINFO(o.hAdapter, KMTQAITYPE_ADAPTERREGISTRYINFO, ctypes.cast(ctypes.byref(reg), ctypes.c_void_p), ctypes.sizeof(reg))
        if gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(q)) == 0:
            out["chip_type"] = reg.ChipType
        return out
    finally:
        gdi32.D3DKMTCloseAdapter(ctypes.byref(D3DKMT_CLOSEADAPTER(o.hAdapter)))


# ---------------------------------------------------------------- SetupAPI
setupapi = ctypes.WinDLL("setupapi")
DIGCF_PRESENT = 0x2
SPDRP_HARDWAREID = 0x1
SPDRP_FRIENDLYNAME = 0xC
SPDRP_DEVICEDESC = 0x0
SPDRP_LOCATION_INFORMATION = 0xD
GUID_DEVCLASS_DISPLAY = GUID.parse("4d36e968-e325-11ce-bfc1-08002be10318")


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("ClassGuid", GUID), ("DevInst", wt.DWORD), ("Reserved", ctypes.c_size_t)]


setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wt.LPCWSTR, wt.HWND, wt.DWORD]
setupapi.SetupDiEnumDeviceInfo.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceRegistryPropertyW.argtypes = [wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), wt.DWORD, ctypes.POINTER(wt.DWORD), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), wt.LPWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD)]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]


def _prop(h: wt.HANDLE, dev: SP_DEVINFO_DATA, prop: int) -> str:
    buf = ctypes.create_unicode_buffer(1024)
    if not setupapi.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(dev), prop, None, buf, ctypes.sizeof(buf), None):
        return ""
    return buf.value  # first string of a MULTI_SZ is enough here


SPDRP_BUSNUMBER = 0x15
SPDRP_ADDRESS = 0x1C


def _dword(h: wt.HANDLE, dev: SP_DEVINFO_DATA, prop: int) -> int | None:
    val = wt.DWORD()
    if not setupapi.SetupDiGetDeviceRegistryPropertyW(h, ctypes.byref(dev), prop, None, ctypes.byref(val), 4, None):
        return None
    return val.value


def setupapi_display_devices() -> list[dict[str, Any]]:
    h = setupapi.SetupDiGetClassDevsW(ctypes.byref(GUID_DEVCLASS_DISPLAY), None, None, DIGCF_PRESENT)
    out: list[dict[str, Any]] = []
    try:
        i = 0
        while True:
            dev = SP_DEVINFO_DATA(cbSize=ctypes.sizeof(SP_DEVINFO_DATA))
            if not setupapi.SetupDiEnumDeviceInfo(h, i, ctypes.byref(dev)):
                break
            iid = ctypes.create_unicode_buffer(512)
            setupapi.SetupDiGetDeviceInstanceIdW(h, ctypes.byref(dev), iid, 512, None)
            # Location text is localized ("PCI-Bus 3, Gerät 0, …") -> use numeric properties.
            bus, addr = _dword(h, dev, SPDRP_BUSNUMBER), _dword(h, dev, SPDRP_ADDRESS)
            pci = f"{bus:02X}:{addr >> 16:02X}.{addr & 0xFFFF}" if bus is not None and addr is not None else None
            out.append(
                {
                    "instance_id": iid.value,
                    "name": _prop(h, dev, SPDRP_FRIENDLYNAME) or _prop(h, dev, SPDRP_DEVICEDESC),
                    "hardware_id": _prop(h, dev, SPDRP_HARDWAREID),
                    "location": _prop(h, dev, SPDRP_LOCATION_INFORMATION),
                    "pci_address": pci,
                    "is_pci": iid.value.upper().startswith("PCI\\"),
                }
            )
            i += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h)
    return out


# ---------------------------------------------------------------- NVML
def nvml_devices() -> list[dict[str, Any]]:
    try:
        import pynvml as n
    except ImportError:
        return []
    try:
        n.nvmlInit()
    except n.NVMLError as e:
        return [{"error": str(e)}]
    out = []
    try:
        for i in range(n.nvmlDeviceGetCount()):
            h = n.nvmlDeviceGetHandleByIndex(i)
            pci = n.nvmlDeviceGetPciInfo(h)
            bus = pci.busId.decode() if isinstance(pci.busId, bytes) else pci.busId
            m = re.match(r"[0-9A-Fa-f]+:([0-9A-Fa-f]+):([0-9A-Fa-f]+)\.(\d)", bus)
            mem = n.nvmlDeviceGetMemoryInfo(h)
            out.append(
                {
                    "name": n.nvmlDeviceGetName(h),
                    "uuid": n.nvmlDeviceGetUUID(h),
                    "pci_bus_id": bus,
                    "pci_address": f"{int(m[1], 16):02X}:{int(m[2], 16):02X}.{m[3]}" if m else None,
                    "vram_total_mib": mem.total // 2**20,
                    "temp_c": n.nvmlDeviceGetTemperature(h, n.NVML_TEMPERATURE_GPU),
                    "power_w": n.nvmlDeviceGetPowerUsage(h) / 1000,
                }
            )
    finally:
        n.nvmlShutdown()
    return out


# ---------------------------------------------------------------- merge
def main() -> int:
    adapters, orders = dxgi_adapters()
    devs = setupapi_display_devices()
    nv = nvml_devices()
    merged = []
    for a in adapters:
        if a["software"]:
            continue
        kmt = kmt_info(a.pop("_luid"))
        a.update({f"kmt_{k}": v for k, v in kmt.items()})
        hwid_prefix = f"PCI\\VEN_{a['vendor_id']}&DEV_{a['device_id']}&SUBSYS_{a['subsys_id']}&REV_{a['revision']}"
        match = [d for d in devs if d["is_pci"] and d["instance_id"].upper().startswith(hwid_prefix) and d["pci_address"] == kmt.get("pci_address")]
        a["setupapi_match"] = match[0]["instance_id"] if len(match) == 1 else f"AMBIGUOUS/NONE ({len(match)})"
        a["gpu_key"] = f"{hwid_prefix}@{kmt.get('pci_address')}" if len(match) == 1 else None
        nvm = [x for x in nv if x.get("pci_address") == kmt.get("pci_address")]
        a["nvml"] = nvm[0] if nvm else None
        merged.append(a)
    non_gpu = [d for d in devs if not d["is_pci"]]
    print(json.dumps({"adapters": merged, "dxgi_order_by_preference": orders, "filtered_non_pci_display_devices": non_gpu}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
