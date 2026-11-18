"""Tray-app side of game mode: start the elevated helper, follow its state, stop and recover."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from gpucc.gamemode.core import FINAL_PHASES, Phase, validate_args
from gpucc.profiles.store import ProfileStore

log = logging.getLogger(__name__)

SETTING_KEY = "gamemode_session"
POLL_MS = 1000
ERROR_CANCELLED = 1223


@dataclass(frozen=True, slots=True)
class Session:
    instance_id: str
    gpu_name: str
    process_name: str
    app_name: str


@dataclass(frozen=True, slots=True)
class Status:
    session: Session
    phase: Phase
    detail: str


def helper_command(session: Session | None, state_dir: Path, enable_only: bool = False) -> tuple[str, str]:
    """(executable, parameters) for the elevated helper; pythonw keeps it windowless."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    params = ["-m", "gpucc.gamemode.helper", "--state-dir", str(state_dir)]
    if session is not None:
        params += ["--instance-id", session.instance_id]
        params += ["--enable-only"] if enable_only else ["--process", session.process_name]
    return str(pythonw if pythonw.exists() else exe), subprocess.list2cmdline(params)


class GameModeService(QObject):
    status_changed = Signal(object)  # Status | None

    def __init__(self, store: ProfileStore, state_dir: Path) -> None:
        super().__init__()
        self._store = store
        self._dir = state_dir
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session: Session | None = None
        self._last: Status | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def active(self) -> bool:
        return self._session is not None

    @property
    def status(self) -> Status | None:
        return self._last

    def start(self, session: Session) -> str | None:
        """Launch the helper via UAC. Returns an error code string or None."""
        validate_args(session.instance_id, session.process_name)
        (self._dir / "stop").unlink(missing_ok=True)
        (self._dir / "state.json").unlink(missing_ok=True)
        from gpucc.platform.win32.elevate import run_elevated

        exe, params = helper_command(session, self._dir)
        pid, err = run_elevated(exe, params)
        if err:
            log.info("game mode not started", extra={"fields": {"error": err}})
            return "cancelled" if err == ERROR_CANCELLED else f"error {err}"
        self._session = session
        self._store.set_setting(SETTING_KEY, json.dumps(_asdict(session)))
        log.info("game mode started", extra={"fields": {"helper_pid": pid, "device": session.instance_id}})
        self._last = Status(session, Phase.STARTING, "")
        self.status_changed.emit(self._last)
        self._timer.start()
        return None

    def request_stop(self) -> None:
        """End the session early – the helper re-enables the GPU."""
        (self._dir / "stop").write_text("stop", encoding="utf-8")

    def _poll(self) -> None:
        if self._session is None:
            self._timer.stop()
            return
        try:
            data = json.loads((self._dir / "state.json").read_text(encoding="utf-8"))
            phase = Phase(data.get("phase", "starting"))
        except (OSError, ValueError):
            return
        status = Status(self._session, phase, str(data.get("detail", "")))
        if status != self._last:
            self._last = status
            self.status_changed.emit(status)
        if phase in FINAL_PHASES:
            self._timer.stop()
            from gpucc.platform.win32.cfgmgr import is_disabled

            if not is_disabled(self._session.instance_id):
                self._store.set_setting(SETTING_KEY, "")
            self._session = None

    # ------------------------------------------------------------------ crash recovery
    def pending_recovery(self) -> Session | None:
        """A previous session left the GPU disabled (helper/app crashed, reboot …)."""
        raw = self._store.get_setting(SETTING_KEY) or ""
        if not raw:
            return None
        try:
            session = Session(**json.loads(raw))
        except (TypeError, ValueError):
            self._store.set_setting(SETTING_KEY, "")
            return None
        from gpucc.platform.win32.cfgmgr import is_disabled

        if is_disabled(session.instance_id):
            return session
        self._store.set_setting(SETTING_KEY, "")
        return None

    def reenable(self, session: Session) -> str | None:
        from gpucc.platform.win32.elevate import run_elevated

        exe, params = helper_command(session, self._dir, enable_only=True)
        _pid, err = run_elevated(exe, params)
        if err:
            return "cancelled" if err == ERROR_CANCELLED else f"error {err}"
        self._session = session
        self._timer.start()
        return None


def _asdict(session: Session) -> dict[str, str]:
    return {
        "instance_id": session.instance_id,
        "gpu_name": session.gpu_name,
        "process_name": session.process_name,
        "app_name": session.app_name,
    }
