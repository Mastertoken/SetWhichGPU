"""Glue between the analysis panel and the data (ADR-0004): overview trends, permission, PresentMon session."""

from __future__ import annotations

import logging
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gpucc.analysis import perflog, presentmon
from gpucc.analysis.overview import WINDOWS_S, trends
from gpucc.analysis.perflog import Access
from gpucc.core.models import TargetApp
from gpucc.i18n import tr
from gpucc.ui.overlay.colors import gpu_colors

if TYPE_CHECKING:
    from gpucc.app import Controller

log = logging.getLogger(__name__)

PERFLOG_ASKED = "perflog_asked"  # setting: the one-time permission question was shown
STATS_FRAMES = 50_000  # frames kept for the statistics (≈ 14 min at 60 fps)
UI_UPDATE_MS = 250


class _Bridge(QObject):
    """PresentMon callbacks arrive on its reader thread → queued into the GUI thread."""

    frame = Signal(object)
    ended = Signal(str)


class AnalysisController(QObject):
    def __init__(self, app: Controller) -> None:
        super().__init__()
        self._app = app
        self._panel = app.overlay.analysis_panel
        self._window_s = WINDOWS_S[0]
        self._access: Access | None = None
        self._session: presentmon.Session | None = None
        self._session_target: TargetApp | None = None
        self._frames: deque[presentmon.Frame] = deque(maxlen=STATS_FRAMES)
        self._end_note = ""
        self._raw: list[str] = []
        self._bridge = _Bridge()
        self._bridge.frame.connect(self._frames.append)
        self._bridge.ended.connect(self._on_session_end)
        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(UI_UPDATE_MS)
        self._ui_timer.timeout.connect(self._update_frames_ui)
        self._panel.window_changed.connect(self._on_window)
        self._panel.start_requested.connect(self.start)
        self._panel.stop_requested.connect(self.stop)
        self._panel.grant_requested.connect(self.grant)
        self._panel.export_requested.connect(self.export_csv)

    # ------------------------------------------------------------------ panel open/close
    def on_toggled(self, open_: bool) -> None:
        if not open_:
            return
        self._access = perflog.access()
        if self._access is not Access.READY and not self._app._store.get_setting(PERFLOG_ASKED):
            self._app._store.set_setting(PERFLOG_ASKED, "1")  # asked exactly once (ADR-0004)
            self.grant(confirm=True)
        self.refresh()
        self._update_frames_ui()

    def _on_window(self, seconds: float) -> None:
        self._window_s = seconds
        self.refresh()

    def refresh(self) -> None:
        """Overview (stage A) from the shared history – called on every snapshot while the panel is open."""
        overlay = self._app.overlay
        if not (overlay.isVisible() and overlay.analysis_open):
            return
        target = self._app._target
        pids = self._app._target_pids if target is not None and target.running else frozenset()
        disc = self._app._discovery
        self._panel.set_overview(
            target.display_name if target is not None else None,
            trends(self._app._history, pids, self._window_s),
            {g.key: g.short_name for g in disc.gpus},
            gpu_colors(disc),
        )
        if self._session is None:
            self._update_frames_ui()

    # ------------------------------------------------------------------ permission (once)
    def grant(self, confirm: bool = False) -> None:
        overlay = self._app.overlay
        with overlay.keep_open():
            if confirm:
                answer = QMessageBox.question(
                    overlay,
                    tr("Frame analysis"),
                    tr(
                        "Frame analysis reads Windows' own performance events (via PresentMon) – nothing is "
                        "injected into games. Windows allows this only for members of the group "
                        "“Performance Log Users”.\n\nSetWhichGPU can add your account to this group once; "
                        "Windows asks for administrator rights for that. It takes effect after your next "
                        "Windows sign-in.\n\nSet up now?"
                    ),
                )
                if answer != QMessageBox.StandardButton.Yes:
                    self._update_frames_ui()
                    return
            self._access, problem = perflog.request_access()
        if problem == "declined":
            self._app.tray.notify(tr("Frame analysis"), tr("The administrator prompt was declined."))
        elif problem:
            self._app.tray.notify(tr("Frame analysis"), tr("The permission could not be set up."), True)
        elif self._access is Access.AFTER_SIGN_IN:
            self._app.tray.notify(
                tr("Frame analysis"), tr("Permission set up – frame analysis works after your next Windows sign-in.")
            )
        self._update_frames_ui()

    # ------------------------------------------------------------------ recording
    def start(self) -> None:
        target = self._app._target
        exe = presentmon.verified_path()
        if self._session is not None or target is None or not target.running or exe is None:
            self._update_frames_ui()
            return
        self._frames.clear()
        self._end_note = ""
        session = presentmon.Session(exe, target.pid, self._bridge.frame.emit, self._bridge.ended.emit)
        try:
            session.start()
        except OSError:
            log.exception("PresentMon could not be started")
            self._end_note = tr("PresentMon could not be started.")
            self._update_frames_ui()
            return
        self._session, self._session_target = session, target
        log.info("frame analysis started")
        self._ui_timer.start()
        self._update_frames_ui()

    def stop(self) -> None:
        if self._session is not None:
            self._session.stop()  # → _on_session_end via the reader thread

    def _on_session_end(self, problem: str) -> None:
        session, target = self._session, self._session_target
        self._session = None
        self._ui_timer.stop()
        if session is not None:
            self._raw = session.header_and_rows
        if problem == "access":
            self._access = perflog.access()
            self._end_note = tr("Windows refused the event recording – the permission is not active yet.")
        elif problem == "ended" and target is not None:
            self._end_note = tr("{app} has exited – recording stopped.", app=target.display_name)
        log.info("frame analysis stopped", extra={"fields": {"frames": len(self._frames), "problem": problem}})
        self._update_frames_ui()

    def shutdown(self) -> None:
        if self._session is not None:
            self._session.stop()

    # ------------------------------------------------------------------ export
    def export_csv(self) -> None:
        if not self._raw:
            return
        name = (self._session_target.exe_name if self._session_target else "frames").rsplit(".", 1)[0]
        default = Path.home() / "Documents" / f"{name}-frames-{time.strftime('%Y%m%d-%H%M%S')}.csv"
        overlay = self._app.overlay
        with overlay.keep_open():
            path, _ = QFileDialog.getSaveFileName(overlay, tr("Save frame data"), str(default), "CSV (*.csv)")
        if not path:
            return
        try:
            Path(path).write_text("\n".join(self._raw) + "\n", encoding="utf-8")
        except OSError as e:
            self._app.tray.notify(tr("Saving failed"), str(e), True)

    # ------------------------------------------------------------------ frames tab state
    def _update_frames_ui(self) -> None:
        target = self._app._target
        exe_ok = presentmon.verified_path() is not None
        access = self._access or perflog.access()
        self._access = access
        recording = self._session is not None
        if recording and self._session_target is not None:
            status = tr("Recording {app} … ({n} frames)", app=self._session_target.display_name, n=len(self._frames))
        elif not exe_ok:
            status = tr("PresentMon is missing in this installation – frame analysis is not available.")
        elif access is Access.MISSING:
            status = tr("Frame analysis needs a one-time Windows permission (group “Performance Log Users”).")
        elif access is Access.AFTER_SIGN_IN:
            status = tr("Permission set up – active after your next Windows sign-in (sign out and in again).")
        elif self._end_note:
            status = self._end_note
        elif target is None or not target.running:
            status = tr("Choose a running application (e.g. a game) to analyse its frames.")
        else:
            status = tr(
                "Records the frames of {app} from Windows events – nothing is injected into the game.",
                app=target.display_name,
            )
        can_start = exe_ok and access is Access.READY and target is not None and target.running
        self._panel.set_frames_state(
            status=status,
            can_start=can_start,
            can_grant=access is Access.MISSING,
            recording=recording,
            can_export=bool(self._raw),
        )
        frames = list(self._frames)
        self._panel.set_frame_stats(presentmon.stats(frames), frames)
