"""Replay a user-selected local capture in an installed RenderDoc process."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from gpucc.analysis.timeline import label, read_bounded

MAX_ACTIONS = 5000


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    depth: int
    event: int
    kind: str
    gpu_ms: float | None
    outputs: str


@dataclass(frozen=True, slots=True)
class Capture:
    api: str
    actions: tuple[Action, ...]
    truncated: bool


def local_executable(path: Path) -> bool:
    try:
        return path.name.lower() == "qrenderdoc.exe" and local_file(path)
    except (OSError, RuntimeError):
        return False


def local_file(path: Path) -> bool:
    return (
        path.is_absolute()
        and not path.drive.startswith("\\\\")
        and not path.resolve().drive.startswith("\\\\")
        and path.is_file()
    )


def installed() -> Path | None:
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if root := os.environ.get(name):
            path = Path(root) / "RenderDoc" / "qrenderdoc.exe"
            if local_executable(path):
                return path
    return None


def read_report(path: Path) -> Capture:
    report = json.loads(read_bounded(path))
    if not isinstance(report, dict) or not isinstance(rows := report.get("actions"), list):
        raise ValueError("Invalid RenderDoc report")
    actions: list[Action] = []
    for row in rows[:MAX_ACTIONS]:
        if not isinstance(row, dict):
            continue
        depth, event, duration = row.get("depth"), row.get("event"), row.get("gpu_ms")
        if type(depth) is not int or type(event) is not int or not (0 <= depth <= 64 and 0 <= event < 2**32):
            continue
        gpu_ms = (
            float(duration)
            if isinstance(duration, (int, float)) and not isinstance(duration, bool) and 0 <= duration <= 1e9
            else None
        )
        actions.append(
            Action(label(row.get("name")), depth, event, label(row.get("kind")), gpu_ms, label(row.get("outputs")))
        )
    if not actions:
        raise ValueError("No RenderDoc actions")
    return Capture(label(report.get("api")), tuple(actions), report.get("truncated") is True or len(rows) > MAX_ACTIONS)


def replay(exe: Path, capture: Path, data: Path) -> Capture:
    if not local_executable(exe) or capture.suffix.lower() != ".rdc" or not local_file(capture):
        raise ValueError("Invalid RenderDoc executable or capture")
    with tempfile.TemporaryDirectory(prefix="renderdoc-", dir=data) as tmp:
        work = Path(tmp)
        script = work / "replay.py"
        output = work / "report.json"
        script.write_text(
            f"CAPTURE = {str(capture.resolve())!r}\nREPORT = {str(output)!r}\nLIMIT = {MAX_ACTIONS}\n" + _REPLAY,
            encoding="utf-8",
        )
        subprocess.run(
            [str(exe), "--python", str(script)],
            cwd=exe.parent,
            check=True,
            timeout=120,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return read_report(output)


# Executed by RenderDoc's embedded interpreter (qrenderdoc --python). qrenderdoc keeps its UI open after a
# script and treats sys.exit() as "script finished", so the script ends the process itself with os._exit():
# 0 after the report is written, 2 on any error – otherwise replay() would wait for its timeout.
_REPLAY = """
import json
import math
import os

try:
    import renderdoc as rd

    capture = rd.OpenCaptureFile()
    try:
        result = capture.OpenFile(CAPTURE, '', None)
        if result.code != rd.ResultCode.Succeeded or capture.LocalReplaySupport() != rd.ReplaySupport.Supported:
            raise RuntimeError('Capture cannot be replayed locally')
        result, controller = capture.OpenCapture(rd.ReplayOptions(), None)
        if result.code != rd.ResultCode.Succeeded:
            raise RuntimeError('Capture replay failed')
        try:
            timings = {}
            if rd.GPUCounter.EventGPUDuration in controller.EnumerateCounters():
                for counter in controller.FetchCounters([rd.GPUCounter.EventGPUDuration]):
                    seconds = counter.value.d
                    if math.isfinite(seconds) and 0 <= seconds <= 1e6:
                        timings[counter.eventId] = seconds * 1000
            structured = controller.GetStructuredFile()
            resources = {str(item.resourceId): item.name for item in controller.GetResources()}
            pending = [(0, item) for item in reversed(controller.GetRootActions())]
            rows = []
            truncated = False
            while pending and len(rows) < LIMIT:
                depth, action = pending.pop()
                flags = action.flags
                kind = next((name for name in ('Drawcall', 'Dispatch', 'Copy', 'Resolve', 'Clear', 'Present')
                             if flags & getattr(rd.ActionFlags, name)), '')
                outputs = [resources.get(str(key), str(key)) for key in list(action.outputs) + [action.depthOut]
                           if key != rd.ResourceId.Null()]
                rows.append(dict(name=action.GetName(structured)[:240], depth=depth, event=action.eventId,
                                 kind=kind, gpu_ms=timings.get(action.eventId), outputs=', '.join(outputs)[:240]))
                if depth < 64:
                    pending.extend((depth + 1, child) for child in reversed(action.children))
                elif action.children:
                    truncated = True
            api = str(controller.GetAPIProperties().pipelineType)
            with open(REPORT, 'w', encoding='utf-8') as output:
                json.dump(dict(api=api, actions=rows, truncated=truncated or bool(pending)), output)
        finally:
            controller.Shutdown()
    finally:
        capture.Shutdown()
except BaseException:
    os._exit(2)
os._exit(0)
"""
