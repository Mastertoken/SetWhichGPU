from gpucc.assignment.win_pref import interpret, parse_fields
from gpucc.core.models import PreferenceKind


def test_parse_fields_preserves_extras():
    assert parse_fields("SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;AutoHDREnable=1;") == {
        "SpecificAdapter": "10DE&2504&881D1043",
        "GpuPreference": "1073741824",
        "AutoHDREnable": "1",
    }
    assert parse_fields("") == {}


def test_no_entry_means_windows_default(discovery, keys):
    p = interpret(None, discovery)
    assert p.kind is PreferenceKind.NONE and p.key == keys["intel"]


def test_classes_resolve_via_dxgi_order(discovery, keys):
    assert interpret("GpuPreference=2;", discovery).key == keys["intel"]  # Unity today
    assert interpret("GpuPreference=1;", discovery).key == keys["amd"]
    p0 = interpret("GpuPreference=0;", discovery)
    assert p0.kind is PreferenceKind.DEFAULT and p0.key == keys["intel"]


def test_specific_adapter(discovery, keys):
    p = interpret("SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;", discovery)
    assert p.kind is PreferenceKind.SPECIFIC and p.key == keys["nvidia"] and not p.stale
    lower = interpret("SpecificAdapter=10de&2504&881d1043;GpuPreference=1073741824;", discovery)
    assert lower.key == keys["nvidia"]


def test_specific_adapter_missing_gpu_is_stale(discovery):
    p = interpret("SpecificAdapter=DEAD&BEEF&00000000;GpuPreference=1073741824;", discovery)
    assert p.stale and p.key is None


def test_garbage(discovery):
    assert interpret("AutoHDREnable=1;", discovery).kind is PreferenceKind.UNKNOWN
    assert interpret("GpuPreference=7;", discovery).kind is PreferenceKind.UNKNOWN
