"""Elevated game-mode helper (started via UAC by the tray app; ADR-0002).

    pythonw -m gpucc.gamemode.helper --instance-id <PCI\\…> --process <game.exe> --state-dir <dir>
    pythonw -m gpucc.gamemode.helper --instance-id <PCI\\…> --enable-only --state-dir <dir>

Only validated arguments are accepted; the only privileged action is pnputil /disable-device or
/enable-device for that one device. Progress goes to <state-dir>/state.json, a file named 'stop'
in the same folder ends the session early (GPU is re-enabled).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

from gpucc.gamemode.core import Phase, SessionContext, run_session, validate_args

log = logging.getLogger("gpucc.gamemode.helper")


class _Device:
    def disable(self, instance_id: str) -> int:
        from gpucc.platform.win32.cfgmgr import pnputil

        rc = pnputil("/disable-device", instance_id)
        log.info("pnputil disable", extra={"fields": {"device": instance_id, "rc": rc}})
        return rc

    def enable(self, instance_id: str) -> int:
        from gpucc.platform.win32.cfgmgr import pnputil

        rc = pnputil("/enable-device", instance_id)
        log.info("pnputil enable", extra={"fields": {"device": instance_id, "rc": rc}})
        return rc

    def is_disabled(self, instance_id: str) -> bool:
        from gpucc.platform.win32.cfgmgr import is_disabled

        return is_disabled(instance_id)


class _Procs:
    def is_running(self, process_name: str) -> bool:
        from gpucc.platform.win32.process import process_names

        return process_name.lower() in process_names()


def write_state(state_dir: Path, phase: Phase, detail: str) -> None:
    tmp = state_dir / "state.json.tmp"
    tmp.write_text(json.dumps({"phase": phase.value, "detail": detail, "ts": time.time()}), encoding="utf-8")
    tmp.replace(state_dir / "state.json")
    log.info("game mode phase", extra={"fields": {"phase": phase.value, "detail": detail}})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gpucc.gamemode.helper")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--process", default="")
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--start-timeout", type=float, default=600.0)
    parser.add_argument("--enable-only", action="store_true")
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    from gpucc.diagnostics.logging import configure_logging

    configure_logging(state_dir)  # gpucc.log inside the game-mode folder
    if args.enable_only:
        validate_args(args.instance_id, "recovery.exe")
        rc = _Device().enable(args.instance_id)
        ok = not _Device().is_disabled(args.instance_id)
        write_state(state_dir, Phase.RESTORED if ok else Phase.FAILED, "" if ok else f"pnputil {rc}")
        return 0 if ok else 1

    validate_args(args.instance_id, args.process)
    stop_file = state_dir / "stop"
    stop_file.unlink(missing_ok=True)
    ctx = SessionContext(
        device=_Device(),
        procs=_Procs(),
        report=lambda phase, detail: write_state(state_dir, phase, detail),
        sleep=time.sleep,
        now=time.monotonic,
        stop_requested=stop_file.exists,
        start_timeout=args.start_timeout,
    )
    write_state(state_dir, Phase.STARTING, "")
    outcome = run_session(args.instance_id, args.process, ctx)
    return 0 if outcome in (Phase.RESTORED, Phase.TIMEOUT) else 1


if __name__ == "__main__":
    sys.exit(main())
