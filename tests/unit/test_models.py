import pytest

from gpucc.core.models import GpuKey, PciAddress, TargetApp, Vendor


def test_pci_roundtrip():
    a = PciAddress.parse("06:00.0")
    assert a == PciAddress(6, 0, 0)
    assert str(a) == "06:00.0"
    assert str(PciAddress(0x75, 0x1F, 3)) == "75:1F.3"


@pytest.mark.parametrize("bad", ["", "6:0", "06:00", "zz:00.0", "06:00.8"])
def test_pci_invalid(bad):
    with pytest.raises(ValueError):
        PciAddress.parse(bad)


def test_gpukey_roundtrip_and_tokens():
    text = "PCI\\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1@06:00.0"
    key = GpuKey.parse(text)
    assert str(key) == text
    assert key.specific_adapter_token == "10DE&2504&881D1043"
    assert GpuKey.parse(text.lower()) == key


def test_gpukey_invalid():
    with pytest.raises(ValueError):
        GpuKey.parse("PCI\\VEN_10DE&DEV_2504@06:00.0")


def test_vendor_from_pci():
    assert Vendor.from_pci_id(0x10DE) is Vendor.NVIDIA
    assert Vendor.from_pci_id(0x8086) is Vendor.INTEL
    assert Vendor.from_pci_id(0x1002) is Vendor.AMD
    assert Vendor.from_pci_id(0x1414) is Vendor.OTHER


def test_target_display_name_prefers_description():
    t = TargetApp(
        1,
        2,
        r"C:\Program Files\Unity\Editor\Unity.exe",
        "Proj",
        "Cls",
        product_name="Unity",
        file_description="Unity Editor",
    )
    assert t.display_name == "Unity Editor"
    assert t.exe_name == "Unity.exe"
    bare = TargetApp(1, 2, r"C:\x\tool.exe", "Title", "Cls")
    assert bare.display_name == "tool"
    npp = TargetApp(
        1,
        2,
        r"C:\npp\notepad++.exe",
        "",
        "",
        product_name="Notepad++",
        file_description="Notepad++ : a free (GNU) source code editor",
    )
    assert npp.display_name == "Notepad++"
    denied = TargetApp(1, 2, None, "Window", "Cls", access_denied=True)
    assert denied.display_name == "Window"
    assert denied.exe_name == "?"
