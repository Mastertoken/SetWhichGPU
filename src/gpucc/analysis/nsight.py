"""Read CUDA, graphics and NVTX intervals from an offline Nsight Systems SQLite export."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from gpucc.analysis.timeline import MAX_EVENTS, Interval, label

# Documented export tables. Trace device/context/stream IDs are only labels in this recording.
_GPU_TABLES = (
    ("CUPTI_ACTIVITY_KIND_KERNEL", "CUDA kernel", "demangledName"),
    ("CUPTI_ACTIVITY_KIND_MEMCPY", "CUDA copy", ""),
    ("CUPTI_ACTIVITY_KIND_MEMSET", "CUDA memset", ""),
)
_MAX_DB_BYTES = 2 * 1024**3


def load(path: Path) -> tuple[Interval, ...]:
    if path.stat().st_size > _MAX_DB_BYTES:
        raise ValueError("Nsight export exceeds the import limit")
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    rows: list[Interval] = []
    deadline = time.monotonic() + 10
    try:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.execute("PRAGMA trusted_schema=OFF")
            conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2 * 1024**2)
            conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 2000)
            tables = {row[1] for row in conn.execute("PRAGMA main.table_list") if row[2] == "table"}
            strings = "StringIds" in tables
            for table, operation, name_column in _GPU_TABLES:
                if table not in tables:
                    continue
                name = "s.value" if name_column and strings else "NULL"
                join = f"LEFT JOIN StringIds s ON s.id = a.{name_column}" if name_column and strings else ""
                query = (
                    f"SELECT a.start, a.end, a.globalPid, a.deviceId, a.contextId, a.streamId, {name} "
                    f"FROM {table} a {join} LIMIT ?"
                )
                for start, end, pid, device, context, stream, text in conn.execute(query, (_remaining(rows),)):
                    track = f"CUDA {label(device)} / {label(context)} / {label(stream)}"
                    _add(rows, start, end, track, process=_pid(pid), name=label(text) or operation)

            if "NVTX_EVENTS" in tables:
                join = "LEFT JOIN StringIds s ON s.id = a.textId" if strings else ""
                name = "coalesce(a.text, s.value)" if strings else "a.text"
                query = (
                    f"SELECT a.start, a.end, a.globalTid, {name} FROM NVTX_EVENTS a {join} "
                    "WHERE a.end IS NOT NULL LIMIT ?"
                )
                for start, end, tid, text in conn.execute(query, (_remaining(rows),)):
                    thread = tid % 0x1000000 if isinstance(tid, int) else ""
                    _add(rows, start, end, f"NVTX / {thread}", process=_pid(tid), name=label(text) or "NVTX")
            _graphics(conn, tables, rows)
    except sqlite3.Error as error:
        raise ValueError("Invalid or unsupported Nsight Systems export") from error
    if not rows:
        raise ValueError("No supported Nsight Systems intervals")
    return tuple(sorted(rows, key=lambda row: row.start_us))


def _remaining(rows: list[Interval]) -> int:
    return MAX_EVENTS + 1 - len(rows)


def _graphics(conn: sqlite3.Connection, tables: set[str], rows: list[Interval]) -> None:
    if "VULKAN_WORKLOAD" in tables:
        for start, end, tid, gpu, context in conn.execute(
            "SELECT start, end, globalTid, gpu, contextId FROM VULKAN_WORKLOAD LIMIT ?", (_remaining(rows),)
        ):
            track = f"Vulkan / {label(gpu)} / {label(context)}"
            _add(rows, start, end, track, process=_pid(tid), name="Vulkan workload")
    if "DXGI_API" in tables:
        strings = "StringIds" in tables
        join = "LEFT JOIN StringIds s ON s.id = a.nameId" if strings else ""
        name_column = "s.value" if strings else "NULL"
        query = f"SELECT a.start, a.end, a.globalTid, a.frameId, {name_column} FROM DXGI_API a {join} LIMIT ?"
        for start, end, tid, frame, name in conn.execute(query, (_remaining(rows),)):
            thread = tid % 0x1000000 if isinstance(tid, int) else ""
            process = _pid(tid)
            frame_key = f"{process} / {frame}" if isinstance(frame, int) and frame > 0 else ""
            _add(rows, start, end, f"DXGI / {thread}", process=process, name=label(name) or "DXGI", frame=frame_key)
    if {"WDDM_DMA_PACKET_START_EVENTS", "WDDM_DMA_PACKET_STOP_EVENTS"} <= tables:
        _dma(conn, tables, rows)


def _dma(conn: sqlite3.Connection, tables: set[str], rows: list[Interval]) -> None:
    engines = {}
    if "ENUM_WDDM_ENGINE_TYPE" in tables:
        engines = {
            key: label(value) for key, value in conn.execute("SELECT id, label FROM ENUM_WDDM_ENGINE_TYPE LIMIT 256")
        }
    query = """
        SELECT start, 0 AS phase, gpu, context, engineType, packetType, ulQueueSubmitSequence,
               uliSubmissionId, queuePacketContext
        FROM WDDM_DMA_PACKET_START_EVENTS
        UNION ALL
        SELECT start, 1 AS phase, gpu, context, engineType, packetType, ulQueueSubmitSequence,
               uliCompletionId, NULL
        FROM WDDM_DMA_PACKET_STOP_EVENTS
        ORDER BY start, phase LIMIT ?
    """
    owners: dict[tuple[object, ...], set[str]] = {}
    if "WDDM_QUEUE_PACKET_START_EVENTS" in tables:
        for gpu, context, sequence, tid in conn.execute(
            "SELECT gpu, context, submitSequence, globalTid FROM WDDM_QUEUE_PACKET_START_EVENTS LIMIT ?",
            (2 * MAX_EVENTS,),
        ):
            if process := _pid(tid):
                owners.setdefault((gpu, context, sequence), set()).add(process)
    pending: dict[tuple[object, ...], tuple[int, str] | None] = {}
    for index, event in enumerate(conn.execute(query, (2 * MAX_EVENTS + 1,))):
        if index >= 2 * MAX_EVENTS:
            raise ValueError("Too many WDDM DMA events")
        ts, phase, gpu, context, engine, packet, sequence, submission, queue_context = event
        if not isinstance(ts, int) or not all(isinstance(value, int) for value in event[2:8]):
            continue
        key = (gpu, context, engine, packet, sequence, submission)
        if phase == 0:
            processes = owners.get((gpu, queue_context, sequence), set())
            owner = next(iter(processes)) if len(processes) == 1 else ""
            pending[key] = None if key in pending else (ts, owner)
        elif pair := pending.pop(key, None):
            begin, owner = pair
            track = f"WDDM / {label(gpu)} / {engines.get(engine) or label(engine)} / {label(context)}"
            _add(rows, begin, ts, track, name=f"DMA #{sequence}", process=owner)


def _pid(identity: object) -> str:
    return str(identity // 0x1000000 % 0x1000000) if isinstance(identity, int) else ""


def _add(
    rows: list[Interval], start: object, end: object, track: str, *, name: str, process: str = "", frame: str = ""
) -> None:
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end:
        return
    low, high = start / 1000, end / 1000
    if low >= high:
        return
    if len(rows) >= MAX_EVENTS:
        raise ValueError("Too many Nsight Systems intervals")
    rows.append(Interval(low, high, track, process, name, frame))
