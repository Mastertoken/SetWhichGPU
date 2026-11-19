"""Frame analysis with Intel PresentMon (MIT, bundled; ADR-0004).

PresentMon reads Windows' own present/GPU events (ETW) – nothing is injected into the game. It needs the
"Performance Log Users" membership (see perflog). Only the bundled binary with the pinned SHA-256 is started,
so a replaced file in the (user-writable) install folder is refused. Its CSV output is parsed defensively.
"""

from __future__ import annotations

import csv
import hashlib
import logging
import math
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

VERSION = "2.6.0"
SHA256 = "b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
EXE_NAME = "PresentMon.exe"
SESSION_NAME = "SetWhichGPU"
MAX_LINE = 8192
MAX_RAW_LINES = 500_000  # CSV export cap (~ 2 h at 60 fps)
GPU_BOUND_RATIO = 0.90  # GPU busy / frame time above this → GPU-limited
CPU_BOUND_RATIO = 0.75  # below this → CPU (or something else) limits


def bundled_path() -> Path:
    """Installed build: <app>/tools/PresentMon.exe; from source: build/vendor/PresentMon.exe (fetch script)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "tools" / EXE_NAME
    return Path(__file__).resolve().parents[3] / "build" / "vendor" / EXE_NAME


_verified: dict[tuple[str, int, int], bool] = {}  # (path, size, mtime) → checksum ok


def verified_path() -> Path | None:
    """The bundled PresentMon if its SHA-256 matches (re-checked whenever the file changes)."""
    path = bundled_path()
    try:
        st = path.stat()
        if st.st_size > 32 << 20:
            return None
        key = (str(path), st.st_size, st.st_mtime_ns)
        if key not in _verified:
            _verified[key] = hashlib.sha256(path.read_bytes()).hexdigest() == SHA256
            if not _verified[key]:
                log.warning("PresentMon binary has an unexpected checksum – not started")
    except OSError:
        return None
    return path if _verified[key] else None


def command(exe: Path, pid: int) -> list[str]:
    if not (isinstance(pid, int) and 0 < pid < 2**32):
        raise ValueError("invalid pid")
    return [
        str(exe),
        "--process_id",
        str(pid),
        "--output_stdout",
        "--no_console_stats",
        "--session_name",
        SESSION_NAME,
        "--stop_existing_session",
        "--terminate_on_proc_exit",
        "--no_track_input",
    ]


# ----------------------------------------------------------------------------- parsing (pure)


@dataclass(frozen=True, slots=True)
class Frame:
    frame_ms: float  # time between this and the previous present (1000 / fps)
    gpu_busy_ms: float | None
    display_latency_ms: float | None
    displayed: bool
    present_mode: str


_FRAME_COLS = ("MsBetweenPresents", "FrameTime", "msBetweenPresents")
_GPU_BUSY_COLS = ("MsGPUBusy", "GPUBusy", "msGPUActive", "MsGPUActive")
_LATENCY_COLS = ("DisplayLatency", "MsDisplayLatency", "msUntilDisplayed", "MsUntilDisplayed")
_DISPLAYED_COLS = ("DisplayedTime", "MsBetweenDisplayChange", "msBetweenDisplayChange")


def _num(value: str | None) -> float | None:
    if value is None or len(value) > 32:
        return None
    try:
        x = float(value)
    except ValueError:
        return None
    return x if math.isfinite(x) and 0 <= x < 60_000 else None


class CsvFrames:
    """Turns PresentMon CSV lines (header first) into Frames. Malformed lines are skipped."""

    def __init__(self) -> None:
        self._index: dict[str, int] | None = None

    def _col(self, row: list[str], names: Sequence[str]) -> str | None:
        assert self._index is not None
        for name in names:
            i = self._index.get(name)
            if i is not None and i < len(row):
                return row[i]
        return None

    def feed(self, line: str) -> Frame | None:
        if not line or len(line) > MAX_LINE:
            return None
        try:
            row = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            return None
        if self._index is None:
            if "Application" in row or "ProcessID" in row:
                self._index = {name.strip(): i for i, name in enumerate(row)}
            return None
        if "Application" in row:  # a repeated header (session restart)
            self._index = {name.strip(): i for i, name in enumerate(row)}
            return None
        frame_ms = _num(self._col(row, _FRAME_COLS))
        if frame_ms is None or frame_ms <= 0:
            return None
        displayed_raw = self._col(row, _DISPLAYED_COLS)
        mode = (self._col(row, ("PresentMode",)) or "")[:48]
        return Frame(
            frame_ms=frame_ms,
            gpu_busy_ms=_num(self._col(row, _GPU_BUSY_COLS)),
            display_latency_ms=_num(self._col(row, _LATENCY_COLS)),
            displayed=displayed_raw not in (None, "", "NA") and (_num(displayed_raw) or 0) > 0,
            present_mode="".join(ch for ch in mode if ch.isprintable()),
        )


@dataclass(frozen=True, slots=True)
class FrameStats:
    frames: int
    fps: float
    low_1: float  # "1 % low": fps at the 99th percentile frame time
    low_01: float
    frame_ms: float
    gpu_busy_pct: float | None  # GPU busy share of the frame time
    latency_ms: float | None
    dropped_pct: float
    present_mode: str
    verdict: str  # "gpu" | "cpu" | "mixed" | ""


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    i = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[i]


def stats(frames: Sequence[Frame]) -> FrameStats | None:
    if not frames:
        return None
    times = [f.frame_ms for f in frames]
    total = sum(times)
    ordered = sorted(times)
    busy = [(f.gpu_busy_ms, f.frame_ms) for f in frames if f.gpu_busy_ms is not None]
    ratio = sum(b for b, _ in busy) / sum(t for _, t in busy) if busy and sum(t for _, t in busy) > 0 else None
    lat = [f.display_latency_ms for f in frames if f.display_latency_ms is not None]
    modes: dict[str, int] = {}
    for f in frames:
        if f.present_mode:
            modes[f.present_mode] = modes.get(f.present_mode, 0) + 1
    verdict = ""
    if ratio is not None:
        verdict = "gpu" if ratio >= GPU_BOUND_RATIO else "cpu" if ratio < CPU_BOUND_RATIO else "mixed"
    return FrameStats(
        frames=len(frames),
        fps=1000.0 * len(frames) / total if total > 0 else 0.0,
        low_1=1000.0 / _percentile(ordered, 0.99),
        low_01=1000.0 / _percentile(ordered, 0.999),
        frame_ms=total / len(frames),
        gpu_busy_pct=None if ratio is None else min(100.0, 100.0 * ratio),
        latency_ms=sum(lat) / len(lat) if lat else None,
        dropped_pct=100.0 * sum(not f.displayed for f in frames) / len(frames),
        present_mode=max(modes, key=lambda m: modes[m]) if modes else "",
        verdict=verdict,
    )


# ----------------------------------------------------------------------------- live session


class Session:
    """Runs PresentMon for one process on a reader thread. Callbacks are called on that thread –
    the Qt side forwards them with queued signals."""

    def __init__(
        self,
        exe: Path,
        pid: int,
        on_frame: Callable[[Frame], None],
        on_end: Callable[[str], None],
    ) -> None:
        self._cmd = command(exe, pid)
        self._on_frame = on_frame
        self._on_end = on_end
        self._proc: subprocess.Popen[str] | None = None
        self._stopping = False
        self.raw: list[str] = []

    def start(self) -> None:
        self._proc = subprocess.Popen(
            self._cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        threading.Thread(target=self._read, name="gpucc-presentmon", daemon=True).start()

    def _read(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        parser = CsvFrames()
        for raw_line in self._proc.stdout:
            line = raw_line.rstrip("\r\n")
            if len(self.raw) < MAX_RAW_LINES:
                self.raw.append(line[:MAX_LINE])
            frame = parser.feed(line)
            if frame is not None:
                self._on_frame(frame)
        self._proc.wait()
        err = (self._proc.stderr.read(4096) if self._proc.stderr else "") or ""
        problem = ""
        if not self._stopping:
            problem = "access" if "access denied" in err.lower() else "ended"
        self._on_end(problem)

    def stop(self) -> None:
        self._stopping = True
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()  # our own child, same user
            # A killed PresentMon can leave its ETW session behind – end it explicitly (same rights).
            try:
                subprocess.Popen(
                    [self._cmd[0], "--terminate_existing_session", "--session_name", SESSION_NAME],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except OSError:
                log.warning("could not end the PresentMon session")

    @property
    def header_and_rows(self) -> list[str]:
        return list(self.raw)
