"""Shared fixtures. Hardware data modelled on a real 3-GPU system (spike S2); instance IDs anonymised."""

from __future__ import annotations

import os

import pytest

from gpucc.core.models import PciAddress
from gpucc.discovery.merge import AdapterRecord, DeviceRecord, merge

GIB = 1 << 30
MIB = 1 << 20

LUID_ARC = 0xFEF3
LUID_AMD = 0x12EE3
LUID_NV = 0x1051C
LUID_ARC_VIRTUAL = 0x3675F
LUID_BASIC = 0x104E9

ADAPTERS = [
    AdapterRecord(
        "Intel(R) Arc(TM) Pro B65 Graphics",
        0x8086,
        0xE222,
        0x60271849,
        0x00,
        32558 * MIB,
        31762 * MIB,
        LUID_ARC,
        False,
        PciAddress(0x03, 0, 0),
    ),
    AdapterRecord(
        "AMD Radeon(TM) Graphics",
        0x1002,
        0x13C0,
        0x364E1849,
        0xC9,
        485 * MIB,
        31762 * MIB,
        LUID_AMD,
        False,
        PciAddress(0x75, 0, 0),
    ),
    AdapterRecord(
        "NVIDIA GeForce RTX 3060",
        0x10DE,
        0x2504,
        0x881D1043,
        0xA1,
        12113 * MIB,
        31762 * MIB,
        LUID_NV,
        False,
        PciAddress(0x06, 0, 0),
    ),
    AdapterRecord(
        "Intel(R) Arc(TM) Pro B65 Graphics",
        0x8086,
        0xE222,
        0x60271849,
        0x00,
        32558 * MIB,
        31762 * MIB,
        LUID_ARC_VIRTUAL,
        False,
        None,
    ),
    AdapterRecord("Microsoft Basic Render Driver", 0x1414, 0x8C, 0, 0, 0, 31762 * MIB, LUID_BASIC, True, None),
]
DEVICES = [
    DeviceRecord(
        "PCI\\VEN_8086&DEV_E222&SUBSYS_60271849&REV_00\\6&0000000&0&00080009",
        "Intel(R) Arc(TM) Pro B65 Graphics",
        PciAddress(0x03, 0, 0),
        "32.0.101.8976",
    ),
    DeviceRecord(
        "PCI\\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1\\4&0000000&0&000B",
        "NVIDIA GeForce RTX 3060",
        PciAddress(0x06, 0, 0),
        "32.0.16.2124",
    ),
    DeviceRecord(
        "PCI\\VEN_1002&DEV_13C0&SUBSYS_364E1849&REV_C9\\4&0000000&0&0041",
        "AMD Radeon(TM) Graphics",
        PciAddress(0x75, 0, 0),
        "32.0.21042.62",
    ),
    DeviceRecord("ROOT\\DISPLAY\\0000", "Meta Virtual Monitor", None, None),
]
ORDER_HIGH = [LUID_ARC, LUID_NV, LUID_AMD, LUID_BASIC, LUID_ARC_VIRTUAL]
ORDER_MIN = [LUID_AMD, LUID_ARC, LUID_NV, LUID_BASIC, LUID_ARC_VIRTUAL]
ORDER_DEFAULT = [LUID_ARC, LUID_AMD, LUID_NV, LUID_ARC_VIRTUAL, LUID_BASIC]


@pytest.fixture(autouse=True)
def german_ui():
    """Most UI assertions are written against the German catalog (the original UI language)."""
    from gpucc.i18n import set_language

    set_language("de")
    yield
    set_language("de")


@pytest.fixture
def discovery():
    return merge(ADAPTERS, DEVICES, ORDER_HIGH, ORDER_MIN, ORDER_DEFAULT)


@pytest.fixture
def keys(discovery):
    by_vendor = {g.vendor.value: g.key for g in discovery.gpus}
    return by_vendor  # {"intel": key, "amd": key, "nvidia": key}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("GPUCC_HW_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set GPUCC_HW_TESTS=1 to run hardware tests")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip)
