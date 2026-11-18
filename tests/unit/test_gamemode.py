"""Game mode (ADR-0002): every path that disabled the GPU must re-enable it."""

from dataclasses import replace

import pytest

from gpucc.core.models import Confidence, GpuSnapshot, ObservedGpu, ProcessGpuUsage, TargetApp
from gpucc.gamemode.core import (
    PNPUTIL_REBOOT_REQUIRED,
    Phase,
    SessionContext,
    preflight,
    run_session,
    validate_args,
)

RTX_ID = "PCI\\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1\\4&0000000&0&000B"
GAME = "AoMRT_s.exe"


# --------------------------------------------------------------------------- validation
@pytest.mark.parametrize(
    ("instance_id", "process"),
    [
        (RTX_ID, "../evil.exe"),
        (RTX_ID, "cmd.exe & calc.exe"),
        (RTX_ID, "game.bat"),
        ("ROOT\\DISPLAY\\0000", GAME),
        ("PCI\\VEN_10DE&DEV_2504 /force", GAME),
        (RTX_ID + " /force", GAME),
    ],
)
def test_helper_rejects_unsafe_arguments(instance_id, process):
    with pytest.raises(ValueError):
        validate_args(instance_id, process)


def test_helper_accepts_real_values():
    validate_args(RTX_ID, GAME)
    validate_args(RTX_ID, "My Friend Pedro - Blood Bullets Bananas.exe")


# --------------------------------------------------------------------------- preflight
@pytest.fixture
def gpus(discovery, keys):
    arc = discovery.by_key(keys["intel"])
    nv = discovery.by_key(keys["nvidia"])
    return replace(discovery, display_gpus=frozenset({arc.key})), arc, nv


def test_preflight_ok_for_rtx_without_monitor(gpus):
    disc, _arc, nv = gpus
    snap = GpuSnapshot(0, (), (ProcessGpuUsage(10, nv.key, {"3D": 99.0}, 4 << 30),))  # the game itself
    check = preflight(gpu=nv, discovery=disc, snapshot=snap, process_name=GAME, game_pids={10})
    assert check.ok and check.warnings == ()


def test_preflight_never_disables_display_gpu_or_last_gpu(gpus, discovery):
    disc, arc, nv = gpus
    assert "Monitor" in " ".join(preflight(gpu=arc, discovery=disc, snapshot=None, process_name=GAME).blockers)
    only = replace(disc, gpus=(nv,))
    assert any("einzige" in b for b in preflight(gpu=nv, discovery=only, snapshot=None, process_name=GAME).blockers)


def test_preflight_blocks_other_compute_and_warns_on_memory(gpus):
    disc, _arc, nv = gpus
    blender = ProcessGpuUsage(20, nv.key, {"Compute (CUDA)": 80.0}, 0)
    check = preflight(gpu=nv, discovery=disc, snapshot=GpuSnapshot(0, (), (blender,)), process_name=GAME)
    assert not check.ok and "rechnen" in check.blockers[0]
    idle = ProcessGpuUsage(21, nv.key, {}, 200 << 20)
    check = preflight(gpu=nv, discovery=disc, snapshot=GpuSnapshot(0, (), (idle,)), process_name=GAME)
    assert check.ok and "Speicher" in check.warnings[0]


def test_preflight_requires_exe_and_single_session(gpus):
    disc, _arc, nv = gpus
    blockers = preflight(gpu=nv, discovery=disc, snapshot=None, process_name=None, session_active=True).blockers
    assert len(blockers) == 2


# --------------------------------------------------------------------------- session state machine
class FakeDevice:
    def __init__(self, disable_rc=0, stays_enabled=False, enable_fails=False):
        self.disabled = False
        self.calls: list[str] = []
        self.disable_rc = disable_rc
        self.stays_enabled = stays_enabled
        self.enable_fails = enable_fails

    def disable(self, _id):
        self.calls.append("disable")
        if not self.stays_enabled:
            self.disabled = True
        return self.disable_rc

    def enable(self, _id):
        self.calls.append("enable")
        if not self.enable_fails:
            self.disabled = False
        return 0

    def is_disabled(self, _id):
        return self.disabled


class Script:
    """Process presence over successive polls, e.g. [True, False, False, True, True, False]."""

    def __init__(self, states, device=None, on_check=None):
        self.states = list(states)
        self.device = device
        self.on_check = on_check

    def is_running(self, _name):
        if self.on_check:
            self.on_check()
        return self.states.pop(0) if len(self.states) > 1 else self.states[0]


def make_ctx(device, procs, **kw):
    clock = {"t": 0.0}
    phases: list[Phase] = []

    def sleep(s):
        clock["t"] += s

    ctx = SessionContext(
        device=device,
        procs=procs,
        report=lambda p, _d: phases.append(p),
        sleep=sleep,
        now=lambda: clock["t"],
        **kw,
    )
    return ctx, phases


def test_full_session_waits_for_exit_then_disables_and_restores():
    dev = FakeDevice()
    # running (on RTX) → closed → [disable] → not yet started → started → playing → exited
    procs = Script([True, True, False, False, True, True, False])
    ctx, phases = make_ctx(dev, procs)
    assert run_session(RTX_ID, GAME, ctx) is Phase.RESTORED
    assert dev.calls == ["disable", "enable"] and not dev.disabled
    assert phases == [Phase.WAITING_FOR_EXIT, Phase.DISABLED, Phase.RUNNING, Phase.RESTORED]


def test_never_disables_while_game_still_runs():
    dev = FakeDevice()
    ctx, phases = make_ctx(dev, Script([True]), exit_timeout=10)
    assert run_session(RTX_ID, GAME, ctx) is Phase.TIMEOUT
    assert dev.calls == []  # GPU never touched
    assert phases[-1] is Phase.TIMEOUT


def test_game_not_started_in_time_re_enables():
    dev = FakeDevice()
    ctx, phases = make_ctx(dev, Script([False]), start_timeout=10)
    assert run_session(RTX_ID, GAME, ctx) is Phase.TIMEOUT
    assert dev.calls == ["disable", "enable"] and not dev.disabled
    assert phases[-1] is Phase.TIMEOUT


def test_device_busy_reboot_required_is_rolled_back():
    dev = FakeDevice(disable_rc=PNPUTIL_REBOOT_REQUIRED, stays_enabled=True)
    ctx, phases = make_ctx(dev, Script([False]))
    assert run_session(RTX_ID, GAME, ctx) is Phase.FAILED
    assert dev.calls == ["disable", "enable"]  # pending disable cancelled
    assert phases[-1] is Phase.FAILED


def test_stop_request_from_tray_re_enables_while_playing():
    dev = FakeDevice()
    stop = {"now": False}
    procs = Script([False, True, True], on_check=lambda: None)
    ctx, _phases = make_ctx(dev, procs, stop_requested=lambda: stop["now"])

    def press_stop_after_start():
        if dev.disabled and procs.states == [True]:
            stop["now"] = True

    procs.on_check = press_stop_after_start
    assert run_session(RTX_ID, GAME, ctx) is Phase.RESTORED
    assert not dev.disabled


def test_exception_after_disable_still_re_enables():
    dev = FakeDevice()

    class Boom:
        calls = 0

        def is_running(self, _name):
            Boom.calls += 1
            if Boom.calls > 1:
                raise RuntimeError("toolhelp failed")
            return False

    ctx, phases = make_ctx(dev, Boom())
    with pytest.raises(RuntimeError):
        run_session(RTX_ID, GAME, ctx)
    assert dev.calls == ["disable", "enable"] and not dev.disabled
    assert phases[-1] is Phase.FAILED


def test_failed_re_enable_is_reported():
    dev = FakeDevice(enable_fails=True)
    ctx, phases = make_ctx(dev, Script([False, True, False]))
    assert run_session(RTX_ID, GAME, ctx) is Phase.FAILED
    assert phases[-1] is Phase.FAILED and dev.disabled


# --------------------------------------------------------------------------- overlay offer
def test_offer_only_when_app_provably_ignores_preference(gpus):
    from gpucc.assignment.win_pref import interpret
    from gpucc.ui.overlay.viewmodel import gamemode_offer

    disc, arc, nv = gpus
    pref_arc = interpret("SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;", disc)
    aom = TargetApp(1, 10, r"D:\Games\AoM\AoMRT_s.exe", "AoM", "c", started_at=2000.0)
    on_rtx = ObservedGpu(nv.key, Confidence.HIGH)
    assert gamemode_offer(aom, pref_arc, on_rtx, 1000.0, disc) == nv.key
    assert gamemode_offer(replace(aom, started_at=500.0), pref_arc, on_rtx, 1000.0, disc) is None  # restart first
    assert gamemode_offer(aom, pref_arc, ObservedGpu(arc.key, Confidence.HIGH), 1000.0, disc) is None  # works
    assert gamemode_offer(aom, pref_arc, on_rtx, None, disc) is None  # external change → order unknown
    pref_rtx = interpret("SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;", disc)
    on_arc = ObservedGpu(arc.key, Confidence.HIGH)
    assert gamemode_offer(aom, pref_rtx, on_arc, 1000.0, disc) is None  # would disable the display GPU


def test_helper_command_quotes_arguments(tmp_path):
    from gpucc.gamemode.service import Session, helper_command

    exe, params = helper_command(Session(RTX_ID, "RTX 3060", "My Game.exe", "My Game"), tmp_path)
    assert exe.lower().endswith(("pythonw.exe", "python.exe"))
    assert "-m gpucc --gamemode-helper" in params and '"My Game.exe"' in params and RTX_ID in params
    _exe, recovery = helper_command(Session(RTX_ID, "RTX", "x.exe", "X"), tmp_path, enable_only=True)
    assert "--enable-only" in recovery and "--process" not in recovery


def test_display_gpus_from_output_counts():
    from conftest import ADAPTERS, DEVICES, LUID_ARC

    from gpucc.discovery.merge import merge

    r = merge(ADAPTERS, DEVICES, output_counts={LUID_ARC: 2})
    assert [r.by_key(k).vendor.value for k in r.display_gpus] == ["intel"]
