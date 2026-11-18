"""Pure merge logic for GPU discovery (no Win32 calls → unit-testable)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from gpucc.core.models import DiscoveryResult, GpuInfo, GpuKey, PciAddress, Vendor

#: Adapters with less dedicated memory than this are treated as integrated (carve-out only).
INTEGRATED_VRAM_THRESHOLD = 1 << 30


@dataclass(frozen=True, slots=True)
class AdapterRecord:
    description: str
    vendor_id: int
    device_id: int
    subsys_id: int
    revision: int
    dedicated_vram: int
    shared_memory: int
    luid: int
    is_software: bool
    pci: PciAddress | None


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    instance_id: str
    name: str
    pci: PciAddress | None
    driver_version: str | None


def merge(
    adapters: Sequence[AdapterRecord],
    devices: Sequence[DeviceRecord],
    order_high_performance: Sequence[int] = (),
    order_minimum_power: Sequence[int] = (),
    order_default: Sequence[int] = (),
    *,
    output_counts: Mapping[int, int] | None = None,
) -> DiscoveryResult:
    gpus: list[GpuInfo] = []
    ignored: list[str] = []
    seen: set[GpuKey] = set()
    for a in adapters:
        if a.is_software:
            ignored.append(f"software adapter: {a.description}")
            continue
        if a.pci is None:
            ignored.append(f"virtual/indirect adapter without PCI address: {a.description}")
            continue
        key = GpuKey(a.vendor_id, a.device_id, a.subsys_id, a.revision, a.pci)
        if key in seen:
            continue
        seen.add(key)
        prefix = key.hardware_id.upper()
        dev = next(
            (d for d in devices if d.instance_id.upper().startswith(prefix) and d.pci == a.pci),
            None,
        )
        gpus.append(
            GpuInfo(
                key=key,
                name=a.description,
                vendor=Vendor.from_pci_id(a.vendor_id),
                luid=a.luid,
                dedicated_vram_bytes=a.dedicated_vram,
                shared_memory_bytes=a.shared_memory,
                is_integrated=a.dedicated_vram < INTEGRATED_VRAM_THRESHOLD,
                instance_id=dev.instance_id if dev else "",
                driver_version=dev.driver_version if dev else None,
            )
        )
    for d in devices:
        if not d.instance_id.upper().startswith("PCI\\"):
            ignored.append(f"not a PCI device: {d.name} ({d.instance_id})")

    by_luid = {g.luid: g.key for g in gpus}

    def first(order: Sequence[int]) -> GpuKey | None:
        return next((by_luid[luid] for luid in order if luid in by_luid), None)

    return DiscoveryResult(
        gpus=tuple(gpus),
        high_performance=first(order_high_performance),
        minimum_power=first(order_minimum_power),
        default=first(order_default),
        ignored=tuple(ignored),
        display_gpus=frozenset(g.key for g in gpus if (output_counts or {}).get(g.luid, 0) > 0),
    )
