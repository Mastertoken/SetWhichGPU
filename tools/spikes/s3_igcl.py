"""Spike S3: Intel Graphics Control Library (ControlLib.dll) via ctypes – read-only telemetry.

Struct layouts follow igcl_api.h (intel/drivers.gpu.control-library). Usage:
    uv run python tools/spikes/s3_igcl.py
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import c_bool, c_char, c_int32, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p
from typing import Any

CTL_RESULT_SUCCESS = 0


def make_version(major: int, minor: int) -> int:
    return (major << 16) | (minor & 0xFFFF)


class ctl_application_id_t(ctypes.Structure):
    _fields_ = [("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", c_uint8 * 8)]


class ctl_init_args_t(ctypes.Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("AppVersion", c_uint32),
        ("flags", c_uint32),
        ("SupportedVersion", c_uint32),
        ("ApplicationUID", ctl_application_id_t),
    ]


class ctl_firmware_version_t(ctypes.Structure):
    _fields_ = [("major_version", c_uint64), ("minor_version", c_uint64), ("build_number", c_uint64)]


class ctl_adapter_bdf_t(ctypes.Structure):
    _fields_ = [("bus", c_uint8), ("device", c_uint8), ("function", c_uint8)]


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", c_uint32), ("HighPart", c_int32)]


class ctl_device_adapter_properties_t(ctypes.Structure):
    _fields_ = [
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("pDeviceID", c_void_p),
        ("device_id_size", c_uint32),
        ("device_type", c_int32),
        ("supported_subfunction_flags", c_uint32),
        ("driver_version", c_uint64),
        ("firmware_version", ctl_firmware_version_t),
        ("pci_vendor_id", c_uint32),
        ("pci_device_id", c_uint32),
        ("rev_id", c_uint32),
        ("num_eus_per_sub_slice", c_uint32),
        ("num_sub_slices_per_slice", c_uint32),
        ("num_slices", c_uint32),
        ("name", c_char * 100),
        ("graphics_adapter_properties", c_uint32),
        ("Frequency", c_uint32),
        ("pci_subsys_id", c_uint16),
        ("pci_subsys_vendor_id", c_uint16),
        ("adapter_bdf", ctl_adapter_bdf_t),
        ("reserved", c_char * 112),
    ]


class ctl_data_value_t(ctypes.Union):
    _fields_ = [
        ("data8", ctypes.c_int8), ("datau8", c_uint8), ("data16", ctypes.c_int16), ("datau16", c_uint16),
        ("data32", c_int32), ("datau32", c_uint32), ("data64", ctypes.c_int64), ("datau64", c_uint64),
        ("datafloat", ctypes.c_float), ("datadouble", ctypes.c_double),
    ]


class ctl_oc_telemetry_item_t(ctypes.Structure):
    _fields_ = [("bSupported", c_bool), ("units", c_int32), ("type", c_int32), ("value", ctl_data_value_t)]

    def get(self) -> float | None:
        if not self.bSupported:
            return None
        attr = ["data8", "datau8", "data16", "datau16", "data32", "datau32", "data64", "datau64", "datafloat", "datadouble"]
        return float(getattr(self.value, attr[self.type])) if 0 <= self.type < len(attr) else None


class ctl_psu_info_t(ctypes.Structure):
    _fields_ = [("bSupported", c_bool), ("psuType", c_int32), ("energyCounter", ctl_oc_telemetry_item_t), ("voltage", ctl_oc_telemetry_item_t)]


T = ctl_oc_telemetry_item_t


class ctl_power_telemetry_t(ctypes.Structure):
    _fields_ = [
        ("Size", c_uint32), ("Version", c_uint8),
        ("timeStamp", T), ("gpuEnergyCounter", T), ("gpuVoltage", T), ("gpuCurrentClockFrequency", T),
        ("gpuCurrentTemperature", T), ("globalActivityCounter", T), ("renderComputeActivityCounter", T),
        ("mediaActivityCounter", T),
        ("gpuPowerLimited", c_bool), ("gpuTemperatureLimited", c_bool), ("gpuCurrentLimited", c_bool),
        ("gpuVoltageLimited", c_bool), ("gpuUtilizationLimited", c_bool),
        ("vramEnergyCounter", T), ("vramVoltage", T), ("vramCurrentClockFrequency", T),
        ("vramCurrentEffectiveFrequency", T), ("vramReadBandwidthCounter", T), ("vramWriteBandwidthCounter", T),
        ("vramCurrentTemperature", T),
        ("vramPowerLimited", c_bool), ("vramTemperatureLimited", c_bool), ("vramCurrentLimited", c_bool),
        ("vramVoltageLimited", c_bool), ("vramUtilizationLimited", c_bool),
        ("totalCardEnergyCounter", T), ("psu", ctl_psu_info_t * 5), ("fanSpeed", T * 5),
        # Version 1 additions
        ("gpuVrTemp", T), ("vramVrTemp", T), ("saVrTemp", T), ("gpuEffectiveClock", T),
        ("gpuOverVoltagePercent", T), ("gpuPowerPercent", T), ("gpuTemperaturePercent", T),
        ("vramReadBandwidth", T), ("vramWriteBandwidth", T),
    ]


def main() -> int:
    try:
        lib = ctypes.CDLL("ControlLib.dll")
    except OSError as e:
        print(json.dumps({"error": f"ControlLib.dll not loadable: {e}"}))
        return 1
    for fn in ("ctlInit", "ctlEnumerateDevices", "ctlGetDeviceProperties", "ctlPowerTelemetryGet", "ctlClose"):
        getattr(lib, fn).restype = c_uint32

    result: dict[str, Any] = {"sizes": {"init": ctypes.sizeof(ctl_init_args_t), "props": ctypes.sizeof(ctl_device_adapter_properties_t), "telemetry": ctypes.sizeof(ctl_power_telemetry_t)}}
    h_api = c_void_p()
    args = ctl_init_args_t(Size=ctypes.sizeof(ctl_init_args_t), Version=0, AppVersion=make_version(1, 1), flags=1)  # 1 = USE_LEVEL_ZERO
    rc = lib.ctlInit(ctypes.byref(args), ctypes.byref(h_api))
    result["ctlInit"] = f"0x{rc:08X}"
    result["supported_version"] = f"{args.SupportedVersion >> 16}.{args.SupportedVersion & 0xFFFF}"
    if rc != CTL_RESULT_SUCCESS:
        print(json.dumps(result, indent=2))
        return 1
    try:
        count = c_uint32(0)
        lib.ctlEnumerateDevices(h_api, ctypes.byref(count), None)
        handles = (c_void_p * count.value)()
        lib.ctlEnumerateDevices(h_api, ctypes.byref(count), handles)
        devices = []
        for h in handles:
            luid = LUID()
            p = ctl_device_adapter_properties_t(Size=ctypes.sizeof(ctl_device_adapter_properties_t), Version=2, pDeviceID=ctypes.cast(ctypes.byref(luid), c_void_p), device_id_size=ctypes.sizeof(LUID))
            rc = lib.ctlGetDeviceProperties(c_void_p(h), ctypes.byref(p))
            dev: dict[str, Any] = {
                "rc_props": f"0x{rc:08X}",
                "name": p.name.decode(errors="replace"),
                "pci": f"{p.pci_vendor_id:04X}:{p.pci_device_id:04X} subsys {p.pci_subsys_vendor_id:04X}{p.pci_subsys_id:04X}",
                "bdf": f"{p.adapter_bdf.bus:02X}:{p.adapter_bdf.device:02X}.{p.adapter_bdf.function}",
                "luid": f"0x{luid.HighPart & 0xFFFFFFFF:08X}_0x{luid.LowPart:08X}",
            }
            samples = []
            for _ in range(2):
                t = ctl_power_telemetry_t(Size=ctypes.sizeof(ctl_power_telemetry_t), Version=1)
                t0 = time.perf_counter()
                rc = lib.ctlPowerTelemetryGet(c_void_p(h), ctypes.byref(t))
                samples.append((rc, t, (time.perf_counter() - t0) * 1000))
                time.sleep(1.0)
            rc, a, call_ms = samples[0]
            _, b, _ = samples[1]
            dev["rc_telemetry"] = f"0x{rc:08X}"
            dev["call_ms"] = round(call_ms, 2)
            if rc == CTL_RESULT_SUCCESS:
                fields = [f for f, _ in ctl_power_telemetry_t._fields_ if f not in ("Size", "Version", "psu", "fanSpeed") and not f.endswith("Limited")]
                dev["supported_fields"] = {f: getattr(b, f).get() for f in fields if getattr(b, f).bSupported}
                ts_a, ts_b = a.timeStamp.get(), b.timeStamp.get()
                if ts_a is not None and ts_b is not None and ts_b > ts_a:
                    dt = ts_b - ts_a
                    def rate(name: str) -> float | None:
                        va, vb = getattr(a, name).get(), getattr(b, name).get()
                        return None if va is None or vb is None else (vb - va) / dt
                    dev["derived"] = {
                        "gpu_power_w": rate("gpuEnergyCounter"),
                        "card_power_w": rate("totalCardEnergyCounter"),
                        "gpu_util_pct": (r * 100 if (r := rate("globalActivityCounter")) is not None else None),
                        "render_util_pct": (r * 100 if (r := rate("renderComputeActivityCounter")) is not None else None),
                    }
                dev["fans_rpm"] = [f.get() for f in b.fanSpeed if f.bSupported]
            devices.append(dev)
        result["devices"] = devices
    finally:
        lib.ctlClose(h_api)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
