"""Intel Graphics Control Library (ControlLib.dll) – read-only telemetry. Layouts per igcl_api.h."""

from __future__ import annotations

import ctypes
from ctypes import c_bool, c_char, c_int32, c_uint8, c_uint16, c_uint32, c_uint64, c_void_p
from dataclasses import dataclass

from gpucc.core.errors import PlatformApiError, SourceUnavailableError
from gpucc.core.models import PciAddress
from gpucc.platform.win32._com import LUID

_CTL_INIT_FLAG_USE_LEVEL_ZERO = 1
_APP_VERSION = (1 << 16) | 1  # CTL_MAKE_VERSION(1, 1)


class _ctl_application_id_t(ctypes.Structure):
    _fields_ = (("Data1", c_uint32), ("Data2", c_uint16), ("Data3", c_uint16), ("Data4", c_uint8 * 8))


class _ctl_init_args_t(ctypes.Structure):
    _fields_ = (
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("AppVersion", c_uint32),
        ("flags", c_uint32),
        ("SupportedVersion", c_uint32),
        ("ApplicationUID", _ctl_application_id_t),
    )


class _ctl_firmware_version_t(ctypes.Structure):
    _fields_ = (("major", c_uint64), ("minor", c_uint64), ("build", c_uint64))


class _ctl_adapter_bdf_t(ctypes.Structure):
    _fields_ = (("bus", c_uint8), ("device", c_uint8), ("function", c_uint8))


class _ctl_device_adapter_properties_t(ctypes.Structure):
    _fields_ = (
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("pDeviceID", c_void_p),
        ("device_id_size", c_uint32),
        ("device_type", c_int32),
        ("supported_subfunction_flags", c_uint32),
        ("driver_version", c_uint64),
        ("firmware_version", _ctl_firmware_version_t),
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
        ("adapter_bdf", _ctl_adapter_bdf_t),
        ("reserved", c_char * 112),
    )


class _ctl_data_value_t(ctypes.Union):
    _fields_ = (
        ("data8", ctypes.c_int8),
        ("datau8", c_uint8),
        ("data16", ctypes.c_int16),
        ("datau16", c_uint16),
        ("data32", c_int32),
        ("datau32", c_uint32),
        ("data64", ctypes.c_int64),
        ("datau64", c_uint64),
        ("datafloat", ctypes.c_float),
        ("datadouble", ctypes.c_double),
    )


_VALUE_ATTRS = (
    "data8",
    "datau8",
    "data16",
    "datau16",
    "data32",
    "datau32",
    "data64",
    "datau64",
    "datafloat",
    "datadouble",
)


class _item(ctypes.Structure):  # ctl_oc_telemetry_item_t
    _fields_ = (("bSupported", c_bool), ("units", c_int32), ("type", c_int32), ("value", _ctl_data_value_t))

    def get(self) -> float | None:
        t = int(self.type)
        if not self.bSupported or not 0 <= t < len(_VALUE_ATTRS):
            return None
        return float(getattr(self.value, _VALUE_ATTRS[t]))


class _ctl_psu_info_t(ctypes.Structure):
    _fields_ = (("bSupported", c_bool), ("psuType", c_int32), ("energyCounter", _item), ("voltage", _item))


class _ctl_power_telemetry_t(ctypes.Structure):
    _fields_ = (
        ("Size", c_uint32),
        ("Version", c_uint8),
        ("timeStamp", _item),
        ("gpuEnergyCounter", _item),
        ("gpuVoltage", _item),
        ("gpuCurrentClockFrequency", _item),
        ("gpuCurrentTemperature", _item),
        ("globalActivityCounter", _item),
        ("renderComputeActivityCounter", _item),
        ("mediaActivityCounter", _item),
        ("gpuPowerLimited", c_bool),
        ("gpuTemperatureLimited", c_bool),
        ("gpuCurrentLimited", c_bool),
        ("gpuVoltageLimited", c_bool),
        ("gpuUtilizationLimited", c_bool),
        ("vramEnergyCounter", _item),
        ("vramVoltage", _item),
        ("vramCurrentClockFrequency", _item),
        ("vramCurrentEffectiveFrequency", _item),
        ("vramReadBandwidthCounter", _item),
        ("vramWriteBandwidthCounter", _item),
        ("vramCurrentTemperature", _item),
        ("vramPowerLimited", c_bool),
        ("vramTemperatureLimited", c_bool),
        ("vramCurrentLimited", c_bool),
        ("vramVoltageLimited", c_bool),
        ("vramUtilizationLimited", c_bool),
        ("totalCardEnergyCounter", _item),
        ("psu", _ctl_psu_info_t * 5),
        ("fanSpeed", _item * 5),
        ("gpuVrTemp", _item),
        ("vramVrTemp", _item),
        ("saVrTemp", _item),
        ("gpuEffectiveClock", _item),
        ("gpuOverVoltagePercent", _item),
        ("gpuPowerPercent", _item),
        ("gpuTemperaturePercent", _item),
        ("vramReadBandwidth", _item),
        ("vramWriteBandwidth", _item),
    )


@dataclass(frozen=True, slots=True)
class IgclDevice:
    handle: int
    name: str
    pci: PciAddress
    luid: int
    vendor_id: int
    device_id: int


@dataclass(frozen=True, slots=True)
class IgclTelemetry:
    """Raw values; energy/activity are monotonically increasing counters."""

    timestamp_s: float | None
    gpu_energy_j: float | None
    card_energy_j: float | None
    gpu_temperature_c: float | None
    vram_temperature_c: float | None
    global_activity_s: float | None
    fan_rpm: float | None


class IgclLibrary:
    def __init__(self) -> None:
        try:
            self._lib = ctypes.CDLL("ControlLib.dll")
        except OSError as e:
            raise SourceUnavailableError(f"ControlLib.dll not loadable: {e}") from e
        for fn in ("ctlInit", "ctlEnumerateDevices", "ctlGetDeviceProperties", "ctlPowerTelemetryGet", "ctlClose"):
            getattr(self._lib, fn).restype = c_uint32
        self._api = c_void_p()
        args = _ctl_init_args_t(
            Size=ctypes.sizeof(_ctl_init_args_t),
            Version=0,
            AppVersion=_APP_VERSION,
            flags=_CTL_INIT_FLAG_USE_LEVEL_ZERO,
        )
        rc = int(self._lib.ctlInit(ctypes.byref(args), ctypes.byref(self._api)))
        if rc:
            raise SourceUnavailableError(f"ctlInit 0x{rc:08X}")

    def devices(self) -> list[IgclDevice]:
        count = c_uint32(0)
        self._lib.ctlEnumerateDevices(self._api, ctypes.byref(count), None)
        handles = (c_void_p * count.value)()
        rc = int(self._lib.ctlEnumerateDevices(self._api, ctypes.byref(count), handles))
        if rc:
            raise PlatformApiError("ctlEnumerateDevices", rc)
        out: list[IgclDevice] = []
        for h in handles:
            luid = LUID()
            p = _ctl_device_adapter_properties_t(
                Size=ctypes.sizeof(_ctl_device_adapter_properties_t),
                Version=2,
                pDeviceID=ctypes.cast(ctypes.byref(luid), c_void_p),
                device_id_size=ctypes.sizeof(LUID),
            )
            if int(self._lib.ctlGetDeviceProperties(c_void_p(h), ctypes.byref(p))):
                continue
            out.append(
                IgclDevice(
                    handle=int(h or 0),
                    name=bytes(p.name).split(b"\x00", 1)[0].decode(errors="replace"),
                    pci=PciAddress(int(p.adapter_bdf.bus), int(p.adapter_bdf.device), int(p.adapter_bdf.function)),
                    luid=luid.as_int(),
                    vendor_id=int(p.pci_vendor_id),
                    device_id=int(p.pci_device_id),
                )
            )
        return out

    def telemetry(self, handle: int) -> IgclTelemetry:
        t = _ctl_power_telemetry_t(Size=ctypes.sizeof(_ctl_power_telemetry_t), Version=1)
        rc = int(self._lib.ctlPowerTelemetryGet(c_void_p(handle), ctypes.byref(t)))
        if rc:
            raise PlatformApiError("ctlPowerTelemetryGet", rc)
        fans = [f.get() for f in t.fanSpeed if f.bSupported]
        return IgclTelemetry(
            timestamp_s=t.timeStamp.get(),
            gpu_energy_j=t.gpuEnergyCounter.get(),
            card_energy_j=t.totalCardEnergyCounter.get(),
            gpu_temperature_c=t.gpuCurrentTemperature.get(),
            vram_temperature_c=t.vramCurrentTemperature.get(),
            global_activity_s=t.globalActivityCounter.get(),
            fan_rpm=fans[0] if fans else None,
        )

    def close(self) -> None:
        if self._api:
            self._lib.ctlClose(self._api)
            self._api = c_void_p()
