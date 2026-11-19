"""Analysis panel (ADR-0004): PresentMon parsing/statistics, overview trends, permission rules."""

import pytest

from gpucc.analysis import perflog, presentmon
from gpucc.analysis.overview import engine_group, trends
from gpucc.analysis.presentmon import CsvFrames, Frame, stats
from gpucc.core.models import GpuSnapshot, GpuTelemetry, ProcessGpuUsage

HEADER = (
    "Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,"
    "CPUStartTime,MsCPUBusy,MsCPUWait,MsGPULatency,MsGPUTime,MsGPUBusy,MsGPUWait,DisplayLatency,DisplayedTime,"
    "MsBetweenPresents"
)


def row(frame_ms, gpu_busy, displayed="16.6", mode="Hardware: Independent Flip", latency="30.0"):
    head = f"game.exe,4242,0x1,DXGI,0,0,1,{mode},1.0,10.0,6.6,0.5"
    return f"{head},{gpu_busy},{gpu_busy},1.0,{latency},{displayed},{frame_ms}"


def test_csv_header_then_frames():
    p = CsvFrames()
    assert p.feed(HEADER) is None
    f = p.feed(row(16.7, 15.2))
    assert f == Frame(16.7, 15.2, 30.0, True, "Hardware: Independent Flip")
    assert p.feed(row(33.3, 10.0, displayed="NA")).displayed is False


@pytest.mark.parametrize(
    "line",
    [
        "",
        "garbage without commas",
        row("nan", 1),
        row("inf", 1),
        row("-5", 1),
        row("1e400", 1),
        row("9" * 40, 1),
        "x" * 10_000,
        '"unterminated,quote',
    ],
)
def test_hostile_or_broken_lines_are_skipped(line):
    p = CsvFrames()
    p.feed(HEADER)
    assert p.feed(line) is None


def test_present_mode_text_is_sanitised_and_capped():
    p = CsvFrames()
    p.feed(HEADER)
    f = p.feed(row(16.7, 10, mode="Flip\x1b[31m<b>" + "x" * 100))
    assert "\x1b" not in f.present_mode and len(f.present_mode) <= 48


def test_stats_and_verdict():
    gpu_bound = [Frame(16.0, 15.5, 30.0, True, "Flip")] * 99 + [Frame(50.0, 49.0, 60.0, True, "Flip")]
    s = stats(gpu_bound)
    assert s.frames == 100 and s.verdict == "gpu"
    assert round(s.fps) == round(1000 * 100 / (16 * 99 + 50))
    assert round(s.low_1) == round(1000 / 16.0) and round(s.low_01) == 20  # 99th/99.9th percentile frame time
    cpu_bound = [Frame(16.7, 6.0, None, i % 10 != 0, "Composed: Flip") for i in range(50)]
    s2 = stats(cpu_bound)
    assert s2.verdict == "cpu" and s2.dropped_pct == pytest.approx(10.0) and s2.latency_ms is None
    assert stats([]) is None


def test_command_and_checksum_guard(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        presentmon.command(tmp_path / "PresentMon.exe", 0)
    cmd = presentmon.command(tmp_path / "PresentMon.exe", 4242)
    assert cmd[1:3] == ["--process_id", "4242"] and "--output_stdout" in cmd
    fake = tmp_path / "PresentMon.exe"
    fake.write_bytes(b"MZ not the real thing")
    monkeypatch.setattr(presentmon, "bundled_path", lambda: fake)
    assert presentmon.verified_path() is None  # wrong checksum → never started


def test_engine_groups():
    assert [engine_group(e) for e in ("3D", "Compute_0", "Cuda", "Copy", "VideoDecode", "Security")] == [
        "3D",
        "Compute",
        "Compute",
        "Copy",
        "Video",
        None,
    ]


def test_trends_per_gpu(discovery, keys):
    arc, nv = keys["intel"], keys["nvidia"]

    def snap(ts, load):
        gpus = (GpuTelemetry(arc, 50.0, {}, None, 0, 61.0, 74.0, ("pdh",)),)
        procs = (
            ProcessGpuUsage(7, arc, {"Compute_0": load, "Copy": 2.0}, 600 << 20),
            ProcessGpuUsage(8, arc, {"3D": 5.0}, 100 << 20),  # child process of the same app
            ProcessGpuUsage(99, arc, {"3D": 90.0}, 1 << 30),  # another app – ignored
            ProcessGpuUsage(7, nv, {"3D": 0.0}, 50 << 20),
        )
        return GpuSnapshot(ts, gpus, procs)

    history = [snap(0.0, 10.0), snap(100.0, 20.0), snap(110.0, 40.0), snap(130.0, 60.0)]
    arc_trend, nv_trend = trends(history, {7, 8}, 30.0)
    assert arc_trend.key == arc and nv_trend.key == nv  # most memory first
    assert [v for _, v in arc_trend.engines["Compute"]] == [20.0, 40.0, 60.0]  # t=0 is outside 30 s
    assert arc_trend.engine_now == {"3D": 5.0, "Compute": 60.0, "Copy": 2.0, "Video": 0.0}
    assert arc_trend.vram_now == 700 << 20 and arc_trend.temperature_now == 61.0
    assert trends(history, set(), 30.0) == ()


@pytest.mark.parametrize(
    "sid",
    ["S-1-5-32-544", "S-1-5-18", "S-1-5-21-1-2-3", "S-1-5-21-1-2-3-4 /add", "", "S-1-5-21-1-2-3-4;calc"],
)
def test_helper_only_accepts_plain_user_sids(sid):
    assert perflog.add_to_group(sid) == perflog.EXIT_BAD_ARGS


def test_helper_rejects_unknown_arguments():
    assert perflog.helper_main(["--evil"]) == perflog.EXIT_BAD_ARGS


def test_permission_is_asked_only_once(qtbot, monkeypatch, discovery):
    from gpucc.ui.analysis_controller import PERFLOG_ASKED, AnalysisController

    calls = []

    class FakeStore:
        def __init__(self):
            self.s = {}

        def get_setting(self, k, default=None):
            return self.s.get(k, default)

        def set_setting(self, k, v):
            self.s[k] = v

    from gpucc.ui.overlay.window import OverlayWindow

    class FakeApp:
        def __init__(self):
            self.overlay = OverlayWindow()
            self._store = FakeStore()
            self._target = None
            self._target_pids = frozenset()
            self._history = []
            self._discovery = discovery

    app = FakeApp()
    qtbot.addWidget(app.overlay)
    monkeypatch.setattr(perflog, "access", lambda: perflog.Access.MISSING)
    ctrl = AnalysisController(app)
    monkeypatch.setattr(ctrl, "grant", lambda confirm=False: calls.append(confirm))
    ctrl.on_toggled(True)
    ctrl.on_toggled(True)
    assert calls == [True] and app._store.s[PERFLOG_ASKED] == "1"
