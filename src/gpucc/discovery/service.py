"""Windows GPU discovery service."""

from __future__ import annotations

import logging

from gpucc.core.errors import GpuccError
from gpucc.core.models import DiscoveryResult
from gpucc.discovery.merge import AdapterRecord, DeviceRecord, merge
from gpucc.platform.win32 import d3dkmt, dxgi, setupapi

log = logging.getLogger(__name__)


class WindowsGpuDiscovery:
    def scan(self) -> DiscoveryResult:
        adapters = [
            AdapterRecord(
                description=a.description,
                vendor_id=a.vendor_id,
                device_id=a.device_id,
                subsys_id=a.subsys_id,
                revision=a.revision,
                dedicated_vram=a.dedicated_video_memory,
                shared_memory=a.shared_system_memory,
                luid=a.luid,
                is_software=a.is_software,
                pci=None if a.is_software else d3dkmt.adapter_pci_address(a.luid),
            )
            for a in dxgi.enum_adapters()
        ]
        try:
            devices = [DeviceRecord(d.instance_id, d.name, d.pci, d.driver_version) for d in setupapi.display_devices()]
        except OSError:
            log.exception("SetupAPI enumeration failed; continuing without driver info")
            devices = []
        try:
            high = dxgi.adapter_order(dxgi.GpuPreferenceOrder.HIGH_PERFORMANCE)
            low = dxgi.adapter_order(dxgi.GpuPreferenceOrder.MINIMUM_POWER)
        except GpuccError:
            log.warning("IDXGIFactory6 not available; preference classes unknown")
            high, low = [], []
        try:
            outputs = dxgi.output_counts()
        except GpuccError:
            log.warning("could not enumerate display outputs")
            outputs = {}
        result = merge(adapters, devices, high, low, [a.luid for a in adapters], output_counts=outputs)
        log.info(
            "gpu discovery",
            extra={
                "fields": {
                    "gpus": [str(g.key) for g in result.gpus],
                    "high_performance": str(result.high_performance),
                    "minimum_power": str(result.minimum_power),
                    "ignored": list(result.ignored),
                }
            },
        )
        return result
