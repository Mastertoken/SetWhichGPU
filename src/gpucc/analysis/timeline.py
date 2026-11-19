"""Bounded, offline GPU/CPU timeline imports with explicit timestamp units."""

from __future__ import annotations

import csv
import gzip
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_BYTES = 32 * 1024 * 1024
MAX_EVENTS = 200_000


@dataclass(frozen=True, slots=True)
class Interval:
    start_us: float
    end_us: float
    track: str
    process: str
    name: str
    frame: str = ""


def read_bounded(path: Path) -> str:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Trace exceeds the import limit")
    return data.decode("utf-8-sig")


def label(value: object) -> str:
    if isinstance(value, (str, int)):
        return "".join(c for c in str(value)[:240] if c.isprintable())
    return ""


def _number(value: object) -> float:
    if not isinstance(value, (str, int, float)):
        raise ValueError("Expected a numeric timestamp")
    return float(value)


def _interval(start: object, end: object, track: str, process: str, name: str, *, frame: str = "") -> Interval | None:
    try:
        low, high = _number(start), _number(end)
    except (ValueError, TypeError, OverflowError):
        return None
    if not (-1e18 <= low < high <= 1e18):
        return None
    return Interval(low, high, track, process, name, frame)


def _csv(text: str) -> list[Interval]:
    result: list[Interval] = []
    reader = csv.DictReader(io.StringIO(text))
    if not {"start_us", "end_us", "engine", "process"}.issubset(reader.fieldnames or ()):
        raise ValueError("Missing timeline CSV columns")
    for index, row in enumerate(reader):
        if index >= MAX_EVENTS:
            raise ValueError("Too many timeline rows")
        track = " / ".join(filter(None, (label(row.get(key)) for key in ("gpu", "engine", "queue"))))
        event = _interval(
            row["start_us"],
            row["end_us"],
            track,
            label(row["process"]),
            label(row.get("name")),
            frame=label(row.get("frame")),
        )
        if event is not None:
            result.append(event)
    return result


def _trace(text: str) -> list[Interval]:
    doc = json.loads(text)
    events = doc.get("traceEvents") if isinstance(doc, dict) else doc
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError("Invalid trace event list")
    names: dict[tuple[str, str], str] = {}
    processes: dict[str, str] = {}
    for event in events:
        if not isinstance(event, dict) or event.get("ph") != "M":
            continue
        args = event.get("args")
        if not isinstance(args, dict):
            continue
        pid, tid = label(event.get("pid")), label(event.get("tid"))
        if event.get("name") == "thread_name":
            names[pid, tid] = label(args.get("name"))
        elif event.get("name") == "process_name":
            processes[pid] = label(args.get("name"))

    result: list[Interval] = []
    stacks: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        pid, tid = label(event.get("pid")), label(event.get("tid"))
        key = (pid, tid)
        phase = event.get("ph")
        if phase == "B":
            stacks.setdefault(key, []).append(event)
            continue
        begin = event
        try:
            if phase == "E" and stacks.get(key):
                begin = stacks[key].pop()
                end = _number(event.get("ts"))
                start = _number(begin.get("ts"))
            elif phase == "X":
                start = _number(event.get("ts"))
                end = start + _number(event.get("dur"))
            else:
                continue
        except (ValueError, TypeError, OverflowError):
            continue
        args = begin.get("args")
        args = args if isinstance(args, dict) else {}
        stream = label(args.get("stream"))
        device = label(args.get("device"))
        track = f"{names[key]} ({pid}:{tid})" if names.get(key) else f"{pid}:{tid}"
        if stream:
            track = " / ".join(filter(None, (device, stream, track)))
        process = f"{processes[pid]} ({pid})" if processes.get(pid) else pid
        item = _interval(start, end, track, process, label(begin.get("name")), frame=label(args.get("frame")))
        if item is not None:
            result.append(item)
    return result


def load_timeline(path: Path) -> tuple[Interval, ...]:
    text = read_bounded(path)
    name = path.name.lower().removesuffix(".gz")
    rows = _csv(text) if name.endswith(".csv") else _trace(text)
    if not rows:
        raise ValueError("No timestamped intervals")
    return tuple(sorted(rows, key=lambda row: row.start_us))


def covered_us(intervals: list[tuple[float, float]]) -> float:
    """Union of intervals on one track, including nested profiler markers."""
    end = -math.inf
    total = 0.0
    for start, stop in sorted(intervals):
        total += max(0.0, stop - max(start, end))
        end = max(end, stop)
    return total
