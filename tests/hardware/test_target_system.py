"""Checks against the real target system. Run with: $env:GPUCC_HW_TESTS='1'; uv run pytest -m hardware"""

import time

import pytest

pytestmark = pytest.mark.hardware


def test_all_three_gpus_and_vendor_telemetry():
    from gpucc.app import default_sampler
    from gpucc.core.models import Vendor
    from gpucc.discovery.service import WindowsGpuDiscovery

    r = WindowsGpuDiscovery().scan()
    vendors = {g.vendor for g in r.gpus}
    assert vendors == {Vendor.NVIDIA, Vendor.INTEL, Vendor.AMD}
    sampler = default_sampler()
    sampler.bind(r.gpus)
    sampler.sample()
    time.sleep(1.0)
    snap = sampler.sample()
    sampler.close()
    by_vendor = {r.by_key(t.key).vendor: t for t in snap.gpus}
    assert by_vendor[Vendor.NVIDIA].temperature_c is not None  # NVML
    assert by_vendor[Vendor.INTEL].temperature_c is not None  # IGCL
    assert by_vendor[Vendor.INTEL].power_w is not None  # IGCL energy delta
