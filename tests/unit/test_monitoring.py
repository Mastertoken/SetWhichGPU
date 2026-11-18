from gpucc.core.models import (
    Confidence,
    GpuReading,
    GpuSnapshot,
    ProcessGpuUsage,
    SourceSample,
)
from gpucc.monitoring.attribution import observe, process_tree
from gpucc.monitoring.merge import merge_readings
from gpucc.monitoring.sampler import MAX_CONSECUTIVE_FAILURES, Sampler
from gpucc.monitoring.sources.igcl import counter_rate, power_from
from gpucc.monitoring.sources.nvml import parse_nvml_bus_id
from gpucc.platform.win32.igcl import IgclTelemetry

MIB = 1 << 20


# --------------------------------------------------------------------------- merge
def test_merge_priorities(discovery, keys):
    nv, arc = keys["nvidia"], keys["intel"]
    samples = {
        "pdh": SourceSample(
            {
                nv: GpuReading(utilization_pct=10, engines={"3D": 10}, vram_used_bytes=100),
                arc: GpuReading(utilization_pct=5, vram_used_bytes=200),
            }
        ),
        "nvml": SourceSample({nv: GpuReading(utilization_pct=99, vram_used_bytes=999, temperature_c=34, power_w=8.8)}),
        "igcl": SourceSample({arc: GpuReading(temperature_c=40, power_w=29)}),
    }
    out = {t.key: t for t in merge_readings(discovery.gpus, samples)}
    assert out[nv].utilization_pct == 99  # max over sources (PDH misses CUDA compute)
    assert out[arc].utilization_pct == 5
    assert out[nv].vram_used_bytes == 100  # PDH still wins for VRAM
    assert out[nv].temperature_c == 34 and out[nv].power_w == 8.8
    assert out[nv].sources == ("nvml", "pdh")
    assert out[arc].temperature_c == 40 and out[arc].power_w == 29
    amd = out[keys["amd"]]
    assert amd.utilization_pct is None and amd.temperature_c is None and amd.sources == ()


def test_cycles_render_on_rtx_visible_although_pdh_reports_zero(discovery, keys):
    """Regression: Blender Cycles (OptiX) on the RTX showed 0 % / empty bar – PDH has no CUDA engine."""
    from gpucc.monitoring.sources.nvml import compute_usage

    nv = keys["nvidia"]
    blender = 4242
    samples = {
        "pdh": SourceSample(
            {nv: GpuReading(utilization_pct=0.0, engines={"3D": 0.0}, vram_used_bytes=3 << 30)},
            (ProcessGpuUsage(blender, nv, {}, 2 << 30),),  # PDH sees only the memory
        ),
        "nvml": SourceSample(
            {nv: GpuReading(utilization_pct=99.0)}, tuple(compute_usage(nv, [blender, blender], 99.0))
        ),
    }
    gpus = {t.key: t for t in merge_readings(discovery.gpus, samples)}
    assert gpus[nv].utilization_pct == 99.0  # blue bar full
    snapshot = GpuSnapshot(0.0, tuple(gpus.values()), (*samples["pdh"].processes, *samples["nvml"].processes))
    o = observe({blender}, [snapshot] * 3)
    assert o.key == nv and o.confidence is Confidence.HIGH  # "active", not just "memory in use"
    assert o.per_gpu[0].dedicated_bytes == 2 << 30  # memory not double counted


def test_compute_usage_split_and_idle(keys):
    from gpucc.monitoring.sources.nvml import compute_usage

    nv = keys["nvidia"]
    usage = compute_usage(nv, [1, 2], 80.0)
    assert [(u.pid, u.engines) for u in usage] == [(1, {"Compute (CUDA)": 40.0}), (2, {"Compute (CUDA)": 40.0})]
    assert compute_usage(nv, [1], 0.0) == [] and compute_usage(nv, [], 50.0) == []


def test_igcl_activity():
    from gpucc.monitoring.sources.igcl import activity_from

    a = IgclTelemetry(10.0, 100.0, 0.0, 40.0, 42.0, 5.0, 1079.0)
    b = IgclTelemetry(11.0, 129.0, 0.0, 41.0, 42.0, 5.4, 1080.0)
    assert round(activity_from(a, b), 1) == 40.0
    assert activity_from(None, b) is None


# --------------------------------------------------------------------------- attribution
def snap(*procs):
    return GpuSnapshot(0.0, (), tuple(procs))


def test_observe_activity_wins(keys):
    arc, nv = keys["intel"], keys["nvidia"]
    hist = [
        snap(
            ProcessGpuUsage(10, arc, {"3D": 1.0, "Copy": 30}, 2 * MIB),
            ProcessGpuUsage(11, nv, {"Compute_0": 60}, 500 * MIB),
        )
    ] * 3
    o = observe({10, 11}, hist)
    assert o.key == nv and o.confidence is Confidence.HIGH
    assert o.per_gpu[0].key == nv and round(o.per_gpu[0].render_pct) == 60


def test_observe_copy_engine_is_not_rendering(keys):
    arc = keys["intel"]
    o = observe({10}, [snap(ProcessGpuUsage(10, arc, {"Copy": 40.0}, 0))])
    assert o.confidence is Confidence.NONE


def test_observe_idle_unity_by_residency(keys):
    arc = keys["intel"]
    hist = [snap(ProcessGpuUsage(21780, arc, {}, 1440 * MIB), ProcessGpuUsage(9000, arc, {}, 725 * MIB))]
    o = observe({21780, 9000}, hist)
    assert o.key == arc and o.confidence is Confidence.MEDIUM
    assert o.per_gpu[0].dedicated_bytes == 2165 * MIB


def test_observe_low_and_none(keys):
    arc, nv = keys["intel"], keys["nvidia"]
    o = observe({1}, [snap(ProcessGpuUsage(1, arc, {}, 10 * MIB), ProcessGpuUsage(1, nv, {}, 300 * MIB))])
    assert o.key == nv and o.confidence is Confidence.LOW
    assert observe({2}, [snap(ProcessGpuUsage(1, nv, {"3D": 50}, MIB))]).confidence is Confidence.NONE
    assert observe({1}, []).confidence is Confidence.NONE


def test_observe_uses_window_average(keys):
    arc = keys["intel"]
    hist = [snap()] * 2 + [snap(ProcessGpuUsage(1, arc, {"3D": 1.2}, 0))]
    o = observe({1}, hist, window=3)
    assert o.confidence is Confidence.NONE  # 1.2 / 3 = 0.4 % < threshold


def test_process_tree():
    parents = {1: 0, 10: 1, 11: 10, 12: 10, 20: 1, 30: 99, 0: 0}
    assert process_tree(10, parents) == {10, 11, 12}
    assert process_tree(1, parents) == {1, 10, 11, 12, 20}
    assert process_tree(77, parents) == {77}


# --------------------------------------------------------------------------- vendor helpers
def test_counter_rate_and_power():
    assert counter_rate(100.0, 10.0, 129.0, 11.0) == 29.0
    assert counter_rate(None, 10.0, 129.0, 11.0) is None
    assert counter_rate(100.0, 10.0, 90.0, 11.0) is None  # counter reset
    assert counter_rate(100.0, 10.0, 110.0, 10.0) is None
    a = IgclTelemetry(10.0, 100.0, 0.0, 40.0, 42.0, 5.0, 1079.0)
    b = IgclTelemetry(11.0, 129.0, 0.0, 41.0, 42.0, 5.1, 1080.0)
    assert power_from(a, b) == 29.0  # card counter stuck at 0 → falls back to GPU energy
    assert power_from(None, b) is None


def test_nvml_bus_id():
    from gpucc.core.models import PciAddress

    assert parse_nvml_bus_id("00000000:06:00.0") == PciAddress(6, 0, 0)
    assert parse_nvml_bus_id("0000:75:00.0") == PciAddress(0x75, 0, 0)
    assert parse_nvml_bus_id("bogus") is None


# --------------------------------------------------------------------------- sampler
class FakeSource:
    def __init__(self, name, sample=None, fail=False, available=True):
        self.name = name
        self._sample = sample or SourceSample()
        self.fail = fail
        self._available = available
        self.calls = 0
        self.bound = None

    @property
    def available(self):
        return self._available

    def bind(self, gpus):
        self.bound = tuple(gpus)

    def sample(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        return self._sample

    def close(self):
        pass


def test_sampler_skips_unavailable_and_disables_failing(discovery, keys):
    good = FakeSource(
        "pdh",
        SourceSample({keys["intel"]: GpuReading(utilization_pct=7)}, (ProcessGpuUsage(1, keys["intel"], {}, MIB),)),
    )
    bad = FakeSource("nvml", fail=True)
    off = FakeSource("igcl", available=False)
    s = Sampler([good, bad, off])
    s.bind(discovery.gpus)
    assert s.source_names == ("pdh", "nvml")
    assert good.bound == discovery.gpus and off.bound is None
    for _ in range(MAX_CONSECUTIVE_FAILURES + 3):
        snapshot = s.sample()
    assert bad.calls == MAX_CONSECUTIVE_FAILURES
    assert snapshot.for_gpu(keys["intel"]).utilization_pct == 7
    assert len(snapshot.processes) == 1
    s.bind(discovery.gpus)  # rebind re-enables
    s.sample()
    assert bad.calls == MAX_CONSECUTIVE_FAILURES + 1
