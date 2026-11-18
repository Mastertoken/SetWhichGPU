"""Which GPU does an application *actually* use? (pure; see docs/spikes/S5_S6_pdh_attribution.md)"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence

from gpucc.core.models import Confidence, GpuKey, GpuSnapshot, ObservedGpu, ProcessGpuSummary

#: Engine types that count as rendering/compute (Copy/Video engines do not).
RENDER_ENGINE_PREFIXES = ("3D", "Compute", "Cuda", "Graphics")
ACTIVITY_THRESHOLD_PCT = 0.5


def is_render_engine(engine: str) -> bool:
    return engine.startswith(RENDER_ENGINE_PREFIXES)


def observe(pids: Collection[int], history: Sequence[GpuSnapshot], window: int = 3) -> ObservedGpu:
    """Attribute the process group ``pids`` to a GPU using the last ``window`` snapshots."""
    recent = list(history)[-window:]
    if not recent or not pids:
        return ObservedGpu(None, Confidence.NONE)
    pidset = set(pids)
    engine_sum: dict[GpuKey, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    memory: dict[GpuKey, int] = defaultdict(int)
    for snap in recent:
        for p in snap.processes:
            if p.pid not in pidset:
                continue
            for eng, v in p.engines.items():
                engine_sum[p.key][eng] += v
    for p in recent[-1].processes:  # memory: latest state, summed over the process group
        if p.pid in pidset:
            memory[p.key] += p.dedicated_bytes

    n = len(recent)
    summaries = []
    for key in set(engine_sum) | set(memory):
        engines = {e: v / n for e, v in engine_sum.get(key, {}).items()}
        render = sum(v for e, v in engines.items() if is_render_engine(e))
        summaries.append(ProcessGpuSummary(key, render, memory.get(key, 0), engines))
    summaries.sort(key=lambda s: (-s.render_pct, -s.dedicated_bytes))
    per_gpu = tuple(summaries)

    active = [s for s in summaries if s.render_pct >= ACTIVITY_THRESHOLD_PCT]
    if active:
        return ObservedGpu(active[0].key, Confidence.HIGH, per_gpu)
    resident = sorted((s for s in summaries if s.dedicated_bytes > 0), key=lambda s: -s.dedicated_bytes)
    if len(resident) == 1:
        return ObservedGpu(resident[0].key, Confidence.MEDIUM, per_gpu)
    if resident:
        return ObservedGpu(resident[0].key, Confidence.LOW, per_gpu)
    return ObservedGpu(None, Confidence.NONE, per_gpu)


def process_tree(root: int, parents: dict[int, int]) -> frozenset[int]:
    """``root`` plus all descendants given a pid → parent-pid map (pure)."""
    children: dict[int, list[int]] = defaultdict(list)
    for pid, ppid in parents.items():
        if pid != ppid:
            children[ppid].append(pid)
    out, stack = {root}, [root]
    while stack:
        for c in children.get(stack.pop(), ()):
            if c not in out:
                out.add(c)
                stack.append(c)
    return frozenset(out)
