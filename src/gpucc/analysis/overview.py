"""Stage A of the analysis panel (ADR-0004): engine load, VRAM and telemetry of one app over time (pure)."""

from __future__ import annotations

from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass

from gpucc.core.models import GpuKey, GpuSnapshot

Points = tuple[tuple[float, float], ...]

#: Engine groups in display order; PDH/NVML engine names are mapped by prefix.
ENGINE_GROUPS = ("3D", "Compute", "Copy", "Video")
_PREFIX = (
    ("3D", "3D"),
    ("Graphics", "3D"),
    ("Compute", "Compute"),
    ("Cuda", "Compute"),
    ("Copy", "Copy"),
    ("Video", "Video"),
)
WINDOWS_S = (30.0, 120.0, 300.0)


def engine_group(engine: str) -> str | None:
    return next((g for prefix, g in _PREFIX if engine.startswith(prefix)), None)


def _window(history: Sequence[GpuSnapshot], window_s: float) -> Iterator[tuple[float, GpuSnapshot]]:
    if not history:
        return
    now = history[-1].timestamp
    for snap in history:
        age = now - snap.timestamp
        if 0 <= age <= window_s:
            yield 1.0 - age / window_s, snap


@dataclass(frozen=True, slots=True)
class GpuTrend:
    key: GpuKey
    engines: dict[str, Points]  # group → load % of the app
    engine_now: dict[str, float]  # latest value per group
    vram: Points  # app's dedicated memory in bytes
    vram_now: int
    temperature_now: float | None
    power_now: float | None


def trends(
    history: Sequence[GpuSnapshot], pids: Collection[int], window_s: float = WINDOWS_S[0]
) -> tuple[GpuTrend, ...]:
    """One trend per GPU the process group used in the window (most memory first)."""
    pidset = set(pids)
    if not pidset or not history:
        return ()
    engines: dict[GpuKey, dict[str, list[tuple[float, float]]]] = {}
    vram: dict[GpuKey, list[tuple[float, float]]] = {}
    for x, snap in _window(history, window_s):
        per_key: dict[GpuKey, dict[str, float]] = {}
        mem: dict[GpuKey, int] = {}
        for p in snap.processes:
            if p.pid not in pidset:
                continue
            groups = per_key.setdefault(p.key, dict.fromkeys(ENGINE_GROUPS, 0.0))
            for eng, v in p.engines.items():
                g = engine_group(eng)
                if g is not None:
                    groups[g] += v
            mem[p.key] = mem.get(p.key, 0) + p.dedicated_bytes
        for key, groups in per_key.items():
            series = engines.setdefault(key, {g: [] for g in ENGINE_GROUPS})
            for g, v in groups.items():
                series[g].append((x, max(0.0, min(100.0, v))))
            vram.setdefault(key, []).append((x, float(mem.get(key, 0))))
    latest = history[-1]
    out = []
    for key, series in engines.items():
        t = latest.for_gpu(key)
        out.append(
            GpuTrend(
                key=key,
                engines={g: tuple(pts) for g, pts in series.items()},
                engine_now={g: (pts[-1][1] if pts else 0.0) for g, pts in series.items()},
                vram=tuple(vram.get(key, [])),
                vram_now=int(vram[key][-1][1]) if vram.get(key) else 0,
                temperature_now=t.temperature_c if t else None,
                power_now=t.power_w if t else None,
            )
        )
    out.sort(key=lambda tr: (-tr.vram_now, -sum(tr.engine_now.values())))
    return tuple(out)
