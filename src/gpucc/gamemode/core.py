"""Game-mode logic (pure): input validation, preflight checks and the session state machine.

Session: wait until the game has exited → disable GPU → wait for the game to start → wait for it to
exit → re-enable GPU. The GPU is re-enabled on every path once it was disabled (try/finally).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from gpucc.core.models import DiscoveryResult, GpuInfo, GpuSnapshot
from gpucc.i18n import tr

PNPUTIL_REBOOT_REQUIRED = 3010
INSTANCE_ID_RE = re.compile(
    r"^PCI\\VEN_[0-9A-F]{4}&DEV_[0-9A-F]{4}&SUBSYS_[0-9A-F]{8}&REV_[0-9A-F]{2}\\[0-9A-Z&_]{1,64}$", re.IGNORECASE
)
PROCESS_RE = re.compile(r"^[\w .()+\-]{1,120}\.exe$", re.IGNORECASE)
ACTIVE_LOAD_PCT = 1.0
DEFAULT_START_TIMEOUT_S = 600.0
DEFAULT_EXIT_TIMEOUT_S = 600.0
POLL_S = 2.0


def validate_args(instance_id: str, process_name: str) -> None:
    """The elevated helper accepts nothing else (AGENTS.md §4)."""
    if not INSTANCE_ID_RE.match(instance_id):
        raise ValueError(f"invalid device instance id: {instance_id!r}")
    if not PROCESS_RE.match(process_name) or "\\" in process_name or "/" in process_name:
        raise ValueError(f"invalid process name: {process_name!r}")


# ----------------------------------------------------------------------------- preflight
@dataclass(frozen=True, slots=True)
class Preflight:
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.blockers


def preflight(
    *,
    gpu: GpuInfo,
    discovery: DiscoveryResult,
    snapshot: GpuSnapshot | None,
    process_name: str | None,
    game_pids: Collection[int] = (),
    session_active: bool = False,
) -> Preflight:
    blockers: list[str] = []
    warnings: list[str] = []
    if session_active:
        blockers.append(tr("Game mode is already active."))
    if not gpu.instance_id or not INSTANCE_ID_RE.match(gpu.instance_id):
        blockers.append(tr("The device could not be identified."))
    if gpu.key in discovery.display_gpus:
        blockers.append(tr("A monitor is connected to this GPU – it is never disabled."))
    if len(discovery.gpus) < 2:
        blockers.append(tr("This is the only GPU."))
    if not process_name or not PROCESS_RE.match(process_name):
        blockers.append(tr("The game's executable is unknown."))
    others = set()
    busy = set()
    for p in snapshot.processes if snapshot else ():
        if p.key != gpu.key or p.pid in game_pids:
            continue
        others.add(p.pid)
        if sum(v for e, v in p.engines.items() if e.startswith(("3D", "Compute", "Cuda"))) >= ACTIVE_LOAD_PCT:
            busy.add(p.pid)
    if busy:
        blockers.append(tr("{n} other process(es) are currently computing on this GPU.", n=len(busy)))
    elif others:
        warnings.append(tr("{n} other process(es) hold memory on this GPU and may lose it.", n=len(others)))
    return Preflight(tuple(blockers), tuple(warnings))


# ----------------------------------------------------------------------------- session
class Phase(StrEnum):
    STARTING = "starting"
    WAITING_FOR_EXIT = "waiting_for_exit"  # game still running on the GPU
    DISABLED = "disabled"  # GPU off, waiting for the game to start
    RUNNING = "running"  # game running without the GPU
    RESTORED = "restored"  # GPU enabled again – session over
    TIMEOUT = "timeout"  # game not started/closed in time – GPU enabled again
    FAILED = "failed"


FINAL_PHASES = frozenset({Phase.RESTORED, Phase.TIMEOUT, Phase.FAILED})


class DeviceControl(Protocol):
    def disable(self, instance_id: str) -> int: ...
    def enable(self, instance_id: str) -> int: ...
    def is_disabled(self, instance_id: str) -> bool: ...


class ProcessWatch(Protocol):
    def is_running(self, process_name: str) -> bool: ...


@dataclass
class SessionContext:
    device: DeviceControl
    procs: ProcessWatch
    report: Callable[[Phase, str], None]
    sleep: Callable[[float], None]
    now: Callable[[], float]
    stop_requested: Callable[[], bool] = lambda: False
    start_timeout: float = DEFAULT_START_TIMEOUT_S
    exit_timeout: float = DEFAULT_EXIT_TIMEOUT_S
    poll: float = POLL_S


def _wait(ctx: SessionContext, condition: Callable[[], bool], timeout: float | None) -> bool:
    """True when condition holds; False on timeout or stop request."""
    start = ctx.now()
    while not condition():
        if ctx.stop_requested() or (timeout is not None and ctx.now() - start > timeout):
            return False
        ctx.sleep(ctx.poll)
    return True


def run_session(instance_id: str, process_name: str, ctx: SessionContext) -> Phase:
    validate_args(instance_id, process_name)
    if ctx.procs.is_running(process_name):
        ctx.report(Phase.WAITING_FOR_EXIT, "")
        if not _wait(ctx, lambda: not ctx.procs.is_running(process_name), ctx.exit_timeout):
            ctx.report(Phase.TIMEOUT, "game not closed – GPU was not disabled")
            return Phase.TIMEOUT
    outcome, detail = Phase.FAILED, "unexpected error"
    disabled = False
    try:
        rc = ctx.device.disable(instance_id)
        disabled = True  # from here on, always re-enable – even after exceptions
        if rc == PNPUTIL_REBOOT_REQUIRED or not ctx.device.is_disabled(instance_id):
            outcome, detail = Phase.FAILED, f"device busy, cannot be disabled without reboot (pnputil {rc})"
        else:
            ctx.report(Phase.DISABLED, "")
            if not _wait(ctx, lambda: ctx.procs.is_running(process_name), ctx.start_timeout):
                outcome, detail = Phase.TIMEOUT, "game was not started"
            else:
                ctx.report(Phase.RUNNING, "")
                _wait(ctx, lambda: not ctx.procs.is_running(process_name), None)
                outcome, detail = Phase.RESTORED, ""
    finally:
        if disabled:
            rc = ctx.device.enable(instance_id)
            if ctx.device.is_disabled(instance_id):
                outcome, detail = Phase.FAILED, f"re-enable failed (pnputil {rc}) – enable the GPU in Device Manager"
        ctx.report(outcome, detail)
    return outcome
