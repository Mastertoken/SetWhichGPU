"""Vendor-neutral telemetry from Windows GPU performance counters."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence

from gpucc.core.errors import GpuccError
from gpucc.core.models import GpuInfo, GpuKey, GpuReading, ProcessGpuUsage, SourceSample
from gpucc.monitoring.pdh_parse import parse_adapter_memory, parse_engine, parse_process_memory

log = logging.getLogger(__name__)

ENGINE_COUNTER = r"\GPU Engine(*)\Utilization Percentage"
PROCESS_MEMORY_COUNTER = r"\GPU Process Memory(*)\Dedicated Usage"
ADAPTER_MEMORY_COUNTER = r"\GPU Adapter Memory(*)\Dedicated Usage"


def build_sample(
    luid_to_key: Mapping[int, GpuKey],
    engines: Mapping[str, float],
    process_memory: Mapping[str, float],
    adapter_memory: Mapping[str, float],
) -> SourceSample:
    """Aggregate raw counter arrays into a SourceSample (pure)."""
    adapter_engines: dict[GpuKey, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    proc_engines: dict[tuple[int, GpuKey], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for name, value in engines.items():
        parsed = parse_engine(name)
        if parsed is None or parsed[1] not in luid_to_key:
            continue
        pid, luid, engine = parsed
        key = luid_to_key[luid]
        adapter_engines[key][engine] += value
        if value > 0:
            proc_engines[(pid, key)][engine] += value

    proc_mem: dict[tuple[int, GpuKey], int] = {}
    for name, value in process_memory.items():
        parsed_mem = parse_process_memory(name)
        if parsed_mem is None or parsed_mem[1] not in luid_to_key:
            continue
        pid, luid = parsed_mem
        k = (pid, luid_to_key[luid])
        proc_mem[k] = proc_mem.get(k, 0) + int(value)

    adapter_mem: dict[GpuKey, int] = {}
    for name, value in adapter_memory.items():
        luid_opt = parse_adapter_memory(name)
        if luid_opt is not None and luid_opt in luid_to_key:
            key = luid_to_key[luid_opt]
            adapter_mem[key] = adapter_mem.get(key, 0) + int(value)

    readings: dict[GpuKey, GpuReading] = {}
    for key in set(luid_to_key.values()):
        eng = {e: min(v, 100.0) for e, v in adapter_engines.get(key, {}).items()}
        readings[key] = GpuReading(
            utilization_pct=max(eng.values(), default=0.0),  # Task-Manager logic
            engines=eng,
            vram_used_bytes=adapter_mem.get(key),
        )
    processes = tuple(
        ProcessGpuUsage(
            pid=pid,
            key=key,
            engines=dict(proc_engines.get((pid, key), {})),
            dedicated_bytes=proc_mem.get((pid, key), 0),
        )
        for (pid, key) in set(proc_engines) | set(proc_mem)
        if proc_mem.get((pid, key), 0) > 0 or proc_engines.get((pid, key))
    )
    return SourceSample(readings=readings, processes=processes)


class PdhSource:
    name = "pdh"

    def __init__(self) -> None:
        from gpucc.platform.win32.pdh import PdhQuery

        self._query: PdhQuery | None = None
        self._luid_to_key: dict[int, GpuKey] = {}
        try:
            q = PdhQuery()
            self._c_engine = q.add(ENGINE_COUNTER)
            self._c_pmem = q.add(PROCESS_MEMORY_COUNTER)
            self._c_amem = q.add(ADAPTER_MEMORY_COUNTER)
            q.collect()  # baseline for rate counters
            self._query = q
        except GpuccError:
            log.exception("PDH GPU counters unavailable")

    @property
    def available(self) -> bool:
        return self._query is not None

    def bind(self, gpus: Sequence[GpuInfo]) -> None:
        self._luid_to_key = {g.luid: g.key for g in gpus}

    def sample(self) -> SourceSample:
        if self._query is None:
            return SourceSample()
        from gpucc.platform.win32.pdh import PDH_FMT_DOUBLE, PDH_FMT_NOCAP100

        q = self._query
        q.collect()
        return build_sample(
            self._luid_to_key,
            q.read(self._c_engine, PDH_FMT_DOUBLE | PDH_FMT_NOCAP100),
            q.read(self._c_pmem),
            q.read(self._c_amem),
        )

    def close(self) -> None:
        if self._query is not None:
            self._query.close()
            self._query = None
