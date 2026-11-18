"""Intel Arc telemetry via IGCL. Power is derived from energy counters (needs two samples)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from gpucc.core.errors import GpuccError
from gpucc.core.models import GpuInfo, GpuKey, GpuReading, SourceSample, Vendor

if TYPE_CHECKING:
    from gpucc.platform.win32.igcl import IgclLibrary, IgclTelemetry

log = logging.getLogger(__name__)

#: Plausibility limit – IGCL sometimes reports "supported" counters that stay at 0.
MAX_PLAUSIBLE_POWER_W = 2000.0


def counter_rate(
    prev_value: float | None, prev_ts: float | None, value: float | None, ts: float | None
) -> float | None:
    """(Δvalue / Δt) for monotonically increasing counters; None if not computable."""
    if None in (prev_value, prev_ts, value, ts):
        return None
    assert prev_value is not None and prev_ts is not None and value is not None and ts is not None
    dt = ts - prev_ts
    dv = value - prev_value
    if dt <= 0 or dv < 0:
        return None
    return dv / dt


def power_from(prev: IgclTelemetry | None, cur: IgclTelemetry) -> float | None:
    if prev is None:
        return None
    for attr in ("card_energy_j", "gpu_energy_j"):
        p = counter_rate(getattr(prev, attr), prev.timestamp_s, getattr(cur, attr), cur.timestamp_s)
        if p is not None and 0 < p < MAX_PLAUSIBLE_POWER_W:
            return p
    return None


def activity_from(prev: IgclTelemetry | None, cur: IgclTelemetry) -> float | None:
    """Global GPU activity in % (busy seconds per second) – includes compute (OpenVINO, oneAPI)."""
    if prev is None:
        return None
    rate = counter_rate(prev.global_activity_s, prev.timestamp_s, cur.global_activity_s, cur.timestamp_s)
    return None if rate is None else max(0.0, min(100.0, rate * 100.0))


class IgclSource:
    name = "igcl"

    def __init__(self) -> None:
        self._lib: IgclLibrary | None = None
        self._handles: dict[GpuKey, int] = {}
        self._prev: dict[GpuKey, IgclTelemetry] = {}
        try:
            from gpucc.platform.win32.igcl import IgclLibrary

            self._lib = IgclLibrary()
        except GpuccError as e:
            log.info("IGCL unavailable: %s", e)

    @property
    def available(self) -> bool:
        return self._lib is not None

    def bind(self, gpus: Sequence[GpuInfo]) -> None:
        self._handles, self._prev = {}, {}
        if self._lib is None:
            return
        by_pci = {g.key.pci: g.key for g in gpus if g.vendor is Vendor.INTEL}
        try:
            for dev in self._lib.devices():
                if dev.pci in by_pci:
                    self._handles[by_pci[dev.pci]] = dev.handle
        except GpuccError:
            log.exception("IGCL device enumeration failed")

    def sample(self) -> SourceSample:
        if self._lib is None:
            return SourceSample()
        readings: dict[GpuKey, GpuReading] = {}
        for key, handle in self._handles.items():
            try:
                cur = self._lib.telemetry(handle)
            except GpuccError:
                log.debug("IGCL telemetry failed for %s", key, exc_info=True)
                continue
            readings[key] = GpuReading(
                utilization_pct=activity_from(self._prev.get(key), cur),
                temperature_c=cur.gpu_temperature_c,
                power_w=power_from(self._prev.get(key), cur),
            )
            self._prev[key] = cur
        return SourceSample(readings=readings)

    def close(self) -> None:
        if self._lib is not None:
            self._lib.close()
            self._lib = None
