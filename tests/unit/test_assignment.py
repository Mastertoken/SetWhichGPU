import pytest

from gpucc.assignment.service import AssignmentService
from gpucc.assignment.support import support_for
from gpucc.assignment.win_pref import compose
from gpucc.core.models import Effect, TargetApp
from gpucc.profiles.store import ProfileStore

EXE = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
NV = "SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;"


class FakeRegistry:
    def __init__(self, values=None, fail=False):
        self.values = dict(values or {})
        self.fail = fail
        self.calls = []

    def read(self, exe):
        return self.values.get(exe)

    def write(self, exe, value):
        self.calls.append(("write", exe, value))
        if self.fail:
            raise PermissionError("denied")
        self.values[exe] = value

    def delete(self, exe):
        self.calls.append(("delete", exe))
        self.values.pop(exe, None)


@pytest.fixture
def store(tmp_path):
    s = ProfileStore(tmp_path / "gpucc.db")
    yield s
    s.close()


# --------------------------------------------------------------------------- compose
def test_compose_specific_and_preserves_extras(keys):
    assert compose(None, keys["nvidia"]) == NV
    assert compose("GpuPreference=2;AutoHDREnable=1;", keys["nvidia"]) == NV + "AutoHDREnable=1;"
    assert compose(NV + "AutoHDREnable=1;", keys["intel"]) == (
        "SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;AutoHDREnable=1;"
    )


def test_compose_windows_default(keys):
    assert compose(NV, None) is None  # nothing left → delete value
    assert compose("GpuPreference=2;", None) is None
    assert compose(NV + "AutoHDREnable=1;", None) == "AutoHDREnable=1;"
    assert compose(None, None) is None


# --------------------------------------------------------------------------- support
def target(**kw):
    base = {"hwnd": 1, "pid": 2, "exe_path": EXE, "title": "", "window_class": ""}
    return TargetApp(**{**base, **kw})


def test_support(discovery, keys):
    ok = support_for(target(), keys["nvidia"], discovery)
    assert ok.supported and ok.effect is Effect.NEXT_APP_START
    assert support_for(target(), None, discovery).supported
    assert not support_for(None, None, discovery).supported
    assert "geschützt" in support_for(target(exe_path=None), None, discovery).reason
    assert "Store-Apps" in support_for(target(is_uwp=True), None, discovery).reason


def test_support_rejects_twins_and_missing(discovery, keys):
    from dataclasses import replace

    from gpucc.core.models import PciAddress

    nv = discovery.by_key(keys["nvidia"])
    twin = replace(nv, key=replace(nv.key, pci=PciAddress(7, 0, 0)), luid=99)
    twins = replace(discovery, gpus=(*discovery.gpus, twin))
    assert "Baugleiche" in support_for(target(), keys["nvidia"], twins).reason
    missing = replace(discovery, gpus=discovery.gpus[:1])
    assert not support_for(target(), keys["nvidia"], missing).supported


# --------------------------------------------------------------------------- service
def test_apply_writes_and_journals(store, keys):
    reg = FakeRegistry({EXE: "GpuPreference=2;AutoHDREnable=1;"})
    svc = AssignmentService(reg, store)
    r = svc.apply(EXE, "Blender", keys["nvidia"])
    assert r.changed and reg.values[EXE] == NV + "AutoHDREnable=1;"
    [entry] = store.journal(EXE)
    assert entry.status == "applied" and entry.old_value == "GpuPreference=2;AutoHDREnable=1;"
    assert entry.new_value == reg.values[EXE] and entry.trigger == "overlay"
    assert svc.last_change_at(EXE) == entry.ts
    assert store.profile_gpu(EXE) == (True, keys["nvidia"])


def test_apply_noop_does_not_touch_registry(store, keys):
    reg = FakeRegistry({EXE: NV})
    r = AssignmentService(reg, store).apply(EXE, "Blender", keys["nvidia"])
    assert not r.changed and reg.calls == [] and store.journal() == []


def test_apply_default_deletes_value(store):
    reg = FakeRegistry({EXE: NV})
    AssignmentService(reg, store).apply(EXE, "Blender", None)
    assert EXE not in reg.values and reg.calls == [("delete", EXE)]
    assert store.profile_gpu(EXE) == (True, None)


def test_apply_failure_is_journaled(store, keys):
    reg = FakeRegistry(fail=True)
    with pytest.raises(PermissionError):
        AssignmentService(reg, store).apply(EXE, "Blender", keys["nvidia"])
    [entry] = store.journal()
    assert entry.status == "failed" and "denied" in entry.detail
    assert AssignmentService(reg, store).last_change_at(EXE) is None


def test_revert_all_restores_original_and_respects_external_changes(store, keys):
    other = r"C:\Games\game.exe"
    third = r"C:\Tools\tool.exe"
    reg = FakeRegistry({EXE: "GpuPreference=2;"})
    svc = AssignmentService(reg, store)
    svc.apply(EXE, "Blender", keys["nvidia"])
    svc.apply(EXE, "Blender", keys["amd"])  # two changes → revert to state before the first
    svc.apply(other, "Game", keys["nvidia"])  # had no value before → delete on revert
    svc.apply(third, "Tool", keys["intel"])
    reg.values[third] = "GpuPreference=1;"  # changed outside SetWhichGPU

    report = svc.revert_all()
    assert set(report.reverted) == {EXE, other}
    assert report.conflicts == (third,)
    assert reg.values[EXE] == "GpuPreference=2;"
    assert other not in reg.values
    assert reg.values[third] == "GpuPreference=1;"  # untouched
    assert svc.revert_all().reverted == ()  # idempotent


# --------------------------------------------------------------------------- store
def test_store_migrations_and_settings(tmp_path):
    path = tmp_path / "db.sqlite"
    s = ProfileStore(path)
    assert s.schema_version == 1
    s.set_setting("hotkey", "Strg+Alt+G")
    s.upsert_profile(EXE, "Blender", None)
    s.close()
    s2 = ProfileStore(path)  # re-open: no re-migration, data kept
    assert s2.schema_version == 1
    assert s2.get_setting("hotkey") == "Strg+Alt+G"
    assert s2.get_setting("missing", "x") == "x"
    assert s2.profiles() == [(EXE, "Blender", None)]
    assert s2.profile_gpu(EXE.upper()) == (True, None)  # case-insensitive paths
    s2.close()
