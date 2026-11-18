"""Clean-up run by the uninstaller: ``SetWhichGPU.exe --uninstall [--revert-preferences]``.

1. Ask a running instance to exit (it ends game mode; the helper re-enables the GPU).
2. If a game-mode session still left a GPU disabled, re-enable it (one UAC prompt).
3. Remove the autostart entry.
4. Optionally restore every GPU preference SetWhichGPU changed (journal based, like the tray command).

The data folder (settings, journal, logs) is removed by the uninstaller itself afterwards.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gpucc.profiles.store import ProfileStore

log = logging.getLogger("gpucc.uninstall")

QUIT_WAIT_S = 20.0
GAMEMODE_WAIT_S = 30.0
REENABLE_WAIT_S = 60.0


@dataclass(frozen=True, slots=True)
class Outcome:
    app_closed: bool
    gpu_reenabled: bool | None  # None = nothing to do
    autostart_removed: bool
    reverted: int | None  # None = not requested


def wait_until(condition: Callable[[], bool], timeout: float, sleep: Callable[[float], None] = time.sleep) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            return False
        sleep(0.25)
    return True


def _instance_running() -> bool:
    from gpucc.__main__ import SINGLETON_NAME
    from gpucc.platform.win32 import user32

    handle, running = user32.acquire_singleton(SINGLETON_NAME)
    user32.release_singleton(handle)
    return running


def close_running_instance() -> bool:
    from gpucc.ui.hotkey import ask_running_instance_to_quit

    if not _instance_running():
        return True
    ask_running_instance_to_quit()
    return wait_until(lambda: not _instance_running(), QUIT_WAIT_S)


def reenable_gpu_if_needed(store: ProfileStore) -> bool | None:
    """Re-enable a GPU a game-mode session left disabled. None if there was nothing to do."""
    from gpucc.diagnostics.paths import data_dir
    from gpucc.gamemode.service import SETTING_KEY, Session, helper_command
    from gpucc.platform.win32.cfgmgr import is_disabled
    from gpucc.platform.win32.elevate import run_elevated

    raw = store.get_setting(SETTING_KEY) or ""
    if not raw:
        return None
    try:
        session = Session(**json.loads(raw))
    except (TypeError, ValueError):
        return None
    # The quitting app asked the helper to stop; give it time to re-enable the GPU itself.
    if wait_until(lambda: not is_disabled(session.instance_id), GAMEMODE_WAIT_S):
        store.set_setting(SETTING_KEY, "")
        return True
    exe, params = helper_command(session, data_dir() / "gamemode", enable_only=True)
    _pid, err = run_elevated(exe, params)
    ok = not err and wait_until(lambda: not is_disabled(session.instance_id), REENABLE_WAIT_S)
    if ok:
        store.set_setting(SETTING_KEY, "")
    log.info("uninstall: re-enable gpu", extra={"fields": {"device": session.instance_id, "ok": ok, "error": err}})
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="SetWhichGPU --uninstall")
    parser.add_argument("--revert-preferences", action="store_true")
    args = parser.parse_args(argv)

    from gpucc.assignment.service import AssignmentService
    from gpucc.branding import LEGACY_AUTOSTART_NAME
    from gpucc.diagnostics.logging import configure_logging
    from gpucc.diagnostics.paths import data_dir, log_dir
    from gpucc.platform.win32.registry import AutostartEntry, UserGpuPreferenceRegistry
    from gpucc.profiles.store import ProfileStore

    configure_logging(log_dir())
    closed = close_running_instance()
    store = ProfileStore(data_dir() / "gpucc.db")
    try:
        gpu = reenable_gpu_if_needed(store)
        removed = True
        for entry in (AutostartEntry(), AutostartEntry(LEGACY_AUTOSTART_NAME)):
            try:
                entry.disable()
            except OSError:
                removed = False
        reverted = None
        if args.revert_preferences:
            report = AssignmentService(UserGpuPreferenceRegistry(), store).revert_all()
            reverted = len(report.reverted)
        outcome = Outcome(closed, gpu, removed, reverted)
    finally:
        store.close()
    log.info("uninstall clean-up", extra={"fields": {k: getattr(outcome, k) for k in Outcome.__slots__}})
    return 0 if closed and gpu is not False else 1
