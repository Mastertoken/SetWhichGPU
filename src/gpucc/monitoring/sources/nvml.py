"""NVIDIA telemetry via NVML (nvidia-ml-py). Matched to GPUs by PCI bus id, never by index."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from gpucc.core.models import GpuInfo, GpuKey, GpuReading, PciAddress, ProcessGpuUsage, SourceSample, Vendor

log = logging.getLogger(__name__)
T = TypeVar("T")


def parse_nvml_bus_id(bus_id: str) -> PciAddress | None:
    """'00000000:06:00.0' → PciAddress(6, 0, 0)."""
    parts = bus_id.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return PciAddress.parse(f"{parts[1][-2:]}:{parts[2]}")
    except ValueError:
        return None


def compute_usage(key: GpuKey, pids: Sequence[int], gpu_util: float | None) -> list[ProcessGpuUsage]:
    """CUDA/OptiX work is invisible to Windows' engine counters → attribute NVML's GPU load to the
    processes NVML lists as compute users (split evenly; memory stays with PDH to avoid double counting)."""
    unique = sorted(set(pids))
    if not unique or not gpu_util:
        return []
    share = gpu_util / len(unique)
    return [ProcessGpuUsage(pid=pid, key=key, engines={"Compute (CUDA)": share}, dedicated_bytes=0) for pid in unique]


class NvmlSource:
    name = "nvml"

    def __init__(self) -> None:
        self._nvml: Any = None
        self._handles: dict[GpuKey, Any] = {}
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
        except Exception as e:
            log.info("NVML unavailable: %s", e)

    @property
    def available(self) -> bool:
        return self._nvml is not None

    def bind(self, gpus: Sequence[GpuInfo]) -> None:
        self._handles = {}
        if self._nvml is None:
            return
        n = self._nvml
        by_pci = {g.key.pci: g.key for g in gpus if g.vendor is Vendor.NVIDIA}
        for i in range(n.nvmlDeviceGetCount()):
            h = n.nvmlDeviceGetHandleByIndex(i)
            bus = n.nvmlDeviceGetPciInfo(h).busId
            pci = parse_nvml_bus_id(bus.decode() if isinstance(bus, bytes) else str(bus))
            if pci in by_pci:
                self._handles[by_pci[pci]] = h

    @staticmethod
    def _call(fn: Callable[..., T], *args: object) -> T | None:
        try:
            return fn(*args)
        except Exception:  # NVMLError_NotSupported etc. → "not available"
            return None

    def sample(self) -> SourceSample:
        if self._nvml is None:
            return SourceSample()
        n = self._nvml
        readings: dict[GpuKey, GpuReading] = {}
        processes: list[ProcessGpuUsage] = []
        for key, h in self._handles.items():
            rates = self._call(n.nvmlDeviceGetUtilizationRates, h)
            mem = self._call(n.nvmlDeviceGetMemoryInfo, h)
            temp = self._call(n.nvmlDeviceGetTemperature, h, n.NVML_TEMPERATURE_GPU)
            milliwatts = self._call(n.nvmlDeviceGetPowerUsage, h)
            util = float(rates.gpu) if rates is not None else None
            readings[key] = GpuReading(
                utilization_pct=util,
                vram_used_bytes=int(mem.used) if mem is not None else None,
                temperature_c=float(temp) if temp is not None else None,
                power_w=float(milliwatts) / 1000.0 if milliwatts is not None else None,
            )
            compute = self._call(n.nvmlDeviceGetComputeRunningProcesses, h) or []
            processes.extend(compute_usage(key, [int(p.pid) for p in compute], util))
        return SourceSample(readings=readings, processes=tuple(processes))

    def close(self) -> None:
        if self._nvml is not None:
            self._call(self._nvml.nvmlShutdown)
            self._nvml = None
