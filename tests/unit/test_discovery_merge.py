from conftest import ADAPTERS, DEVICES, LUID_ARC, LUID_NV

from gpucc.core.models import GpuKey, Vendor
from gpucc.discovery.merge import merge


def test_target_system_three_gpus(discovery):
    assert [str(g.key) for g in discovery.gpus] == [
        "PCI\\VEN_8086&DEV_E222&SUBSYS_60271849&REV_00@03:00.0",
        "PCI\\VEN_1002&DEV_13C0&SUBSYS_364E1849&REV_C9@75:00.0",
        "PCI\\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1@06:00.0",
    ]


def test_virtual_and_software_adapters_ignored(discovery):
    assert len(discovery.gpus) == 3
    text = " | ".join(discovery.ignored)
    assert "software adapter: Microsoft Basic Render Driver" in text
    assert "without PCI address" in text
    assert "Meta Virtual Monitor" in text


def test_integrated_detection_and_driver(discovery, keys):
    amd = discovery.by_key(keys["amd"])
    arc = discovery.by_key(keys["intel"])
    assert amd is not None and amd.is_integrated
    assert arc is not None and not arc.is_integrated
    assert arc.driver_version == "32.0.101.8976"
    assert arc.instance_id.startswith("PCI\\VEN_8086")


def test_preference_class_mapping(discovery, keys):
    assert discovery.high_performance == keys["intel"]
    assert discovery.minimum_power == keys["amd"]
    assert discovery.default == keys["intel"]


def test_lookup_helpers(discovery):
    assert discovery.by_luid(LUID_NV).vendor is Vendor.NVIDIA
    assert discovery.by_luid(123) is None
    assert discovery.by_luid(LUID_ARC).short_name == "Arc Pro B65"


def test_works_without_setupapi():
    r = merge(ADAPTERS, [], [], [], [])
    assert len(r.gpus) == 3
    assert all(g.instance_id == "" and g.driver_version is None for g in r.gpus)
    assert r.high_performance is None


def test_identical_twins_distinguished_by_location():
    from dataclasses import replace

    from gpucc.core.models import PciAddress

    twin = replace(ADAPTERS[2], luid=0x999, pci=PciAddress(0x07, 0, 0))
    r = merge([ADAPTERS[2], twin], DEVICES)
    assert len({g.key for g in r.gpus}) == 2
    assert {g.key.specific_adapter_token for g in r.gpus} == {"10DE&2504&881D1043"}
    assert all(isinstance(g.key, GpuKey) for g in r.gpus)
