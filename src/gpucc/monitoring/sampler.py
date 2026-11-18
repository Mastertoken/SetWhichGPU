"""Combines all telemetry sources into one GpuSnapshot per tick."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from gpucc.core.models import GpuInfo, GpuSnapshot, ProcessGpuUsage, SourceSample
from gpucc.core.ports import TelemetrySource
from gpucc.monitoring.merge import merge_readings

log = logging.getLogger(__name__)

#: A source is disabled after this many consecutive failures (until the next rebind).
MAX_CONSECUTIVE_FAILURES = 5


class Sampler:
    def __init__(self, sources: Sequence[TelemetrySource]) -> None:
        self._sources = [s for s in sources if s.available]
        self._failures: dict[str, int] = {}
        self._gpus: tuple[GpuInfo, ...] = ()
        log.info("telemetry sources", extra={"fields": {"active": [s.name for s in self._sources]}})

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self._sources)

    def bind(self, gpus: Sequence[GpuInfo]) -> None:
        self._gpus = tuple(gpus)
        self._failures.clear()
        for s in self._sources:
            try:
                s.bind(self._gpus)
            except Exception:
                log.exception("bind failed for source %s", s.name)
                self._failures[s.name] = MAX_CONSECUTIVE_FAILURES

    def sample(self) -> GpuSnapshot:
        samples: dict[str, SourceSample] = {}
        processes: list[ProcessGpuUsage] = []
        for s in self._sources:
            if self._failures.get(s.name, 0) >= MAX_CONSECUTIVE_FAILURES:
                continue
            try:
                sample = s.sample()
            except Exception:
                n = self._failures.get(s.name, 0) + 1
                self._failures[s.name] = n
                log.exception("sample failed for %s (%d/%d)", s.name, n, MAX_CONSECUTIVE_FAILURES)
                continue
            self._failures[s.name] = 0
            samples[s.name] = sample
            processes.extend(sample.processes)  # PDH: engines + memory, NVML: CUDA compute users
        return GpuSnapshot(time.time(), merge_readings(self._gpus, samples), tuple(processes))

    def close(self) -> None:
        for s in self._sources:
            try:
                s.close()
            except Exception:
                log.exception("close failed for %s", s.name)
