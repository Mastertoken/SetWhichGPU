"""Field-wise merge of partial readings from several telemetry sources (pure)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from gpucc.core.models import GpuInfo, GpuReading, GpuTelemetry, SourceSample

#: Per field: which source wins. PDH first for VRAM → identical semantics on all vendors.
FIELD_PRIORITY: Mapping[str, tuple[str, ...]] = {
    "vram_used_bytes": ("pdh", "nvml", "igcl"),
    "temperature_c": ("nvml", "igcl", "pdh"),
    "power_w": ("nvml", "igcl", "pdh"),
}
#: Utilization is the *maximum* over all sources: Windows' GPU engine counters do not expose
#: CUDA/OptiX compute on NVIDIA (no Compute/Cuda engine), so a Cycles render shows 0 % in PDH
#: while NVML reports the real load. Each source can only under-report, never over-report.
UTILIZATION_SOURCES = ("pdh", "nvml", "igcl")


def merge_readings(gpus: Sequence[GpuInfo], samples: Mapping[str, SourceSample]) -> tuple[GpuTelemetry, ...]:
    out: list[GpuTelemetry] = []
    for gpu in gpus:
        per_source: dict[str, GpuReading] = {
            name: s.readings[gpu.key] for name, s in samples.items() if gpu.key in s.readings
        }
        values: dict[str, object] = {}
        used: set[str] = set()
        for field, order in FIELD_PRIORITY.items():
            for src in order:
                r = per_source.get(src)
                v = getattr(r, field) if r is not None else None
                if v is not None:
                    values[field] = v
                    used.add(src)
                    break
        util_values = {
            src: r.utilization_pct
            for src in UTILIZATION_SOURCES
            if (r := per_source.get(src)) is not None and r.utilization_pct is not None
        }
        util = max(util_values.values()) if util_values else None
        used.update(util_values)
        engines = next((r.engines for r in per_source.values() if r.engines), {})
        vram = values.get("vram_used_bytes")
        temp = values.get("temperature_c")
        power = values.get("power_w")
        out.append(
            GpuTelemetry(
                key=gpu.key,
                utilization_pct=min(100.0, float(util)) if util is not None else None,
                engines=dict(engines),
                vram_used_bytes=int(vram) if isinstance(vram, (int, float)) else None,
                vram_total_bytes=gpu.dedicated_vram_bytes,
                temperature_c=float(temp) if isinstance(temp, (int, float)) else None,
                power_w=float(power) if isinstance(power, (int, float)) else None,
                sources=tuple(sorted(used)),
            )
        )
    return tuple(out)
