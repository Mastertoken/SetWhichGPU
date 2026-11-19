"""Composition root and controller: wires discovery, monitoring, app detection and UI."""

from __future__ import annotations

import logging
import os
from collections import deque

from PySide6.QtCore import QObject, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication, QScreen
from PySide6.QtWidgets import QApplication, QMessageBox

from gpucc.assignment.service import AssignmentService
from gpucc.assignment.support import support_for
from gpucc.assignment.win_pref import interpret
from gpucc.branding import APP_NAME, LANGUAGE_SETTING, LOCALAI_SETTING, RESTART_FLAG
from gpucc.core.hotkey import DEFAULT_HOTKEY, Hotkey, parse_hotkey
from gpucc.core.models import (
    DiscoveryResult,
    FullscreenState,
    GpuKey,
    GpuSnapshot,
    PreferredGpu,
    TargetApp,
)
from gpucc.core.ports import ForegroundProbe, GpuDiscovery, PreferenceRegistry
from gpucc.diagnostics.paths import data_dir, log_dir
from gpucc.gamemode.core import FINAL_PHASES, Phase, preflight
from gpucc.gamemode.service import GameModeService, Session
from gpucc.gamemode.service import Status as GameModeStatus
from gpucc.i18n import SYSTEM, language, resolve_language, tr
from gpucc.launch import self_command, self_command_line
from gpucc.library.scanner import learn_render_exes
from gpucc.library.service import LibraryService
from gpucc.localai.runtimes import ModelReport, runtime_for
from gpucc.localai.worker import LocalAiThread
from gpucc.monitoring.attribution import observe
from gpucc.monitoring.sampler import Sampler
from gpucc.monitoring.worker import INTERVAL_ACTIVE_MS, INTERVAL_IDLE_MS, MonitoringThread
from gpucc.platform.win32 import process, user32
from gpucc.platform.win32.registry import AutostartEntry
from gpucc.profiles.store import ProfileStore
from gpucc.ui.hotkey import HotkeyService
from gpucc.ui.overlay.applist import background_candidates, build_app_list, valid_program_path, with_game
from gpucc.ui.overlay.viewmodel import build_state
from gpucc.ui.overlay.window import OverlayWindow
from gpucc.ui.tray import TrayService

log = logging.getLogger(__name__)

HISTORY_LENGTH = 40  # ≥ 30 s of 1-s samples for the load charts (attribution uses only the last 3)
TREE_REFRESH_EVERY = 5  # snapshots
FOLLOW_DEBOUNCE_MS = 200
LIST_REFRESH_EVERY = 3  # snapshots (~3 s while the overlay is open)
CUSTOM_PREFIX = "custom_app:"  # settings key prefix: programs added by the user (value = exe path)
LIST_FIRST_BUILD_DELAY_MS = 30  # let the loading animation paint before the first list is built
LOCALAI_EVERY = 3  # snapshots (~3 s) between "loaded models" queries while such a runtime is shown
LEARNED_PREFIX = "learned_exe:"
LEARN_MIN_VRAM = 64 << 20  # a process counts as "using the GPU" from this much dedicated memory
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


def default_sampler() -> Sampler:
    from gpucc.monitoring.sources.igcl import IgclSource
    from gpucc.monitoring.sources.nvml import NvmlSource
    from gpucc.monitoring.sources.pdh import PdhSource

    return Sampler([PdhSource(), NvmlSource(), IgclSource()])


def configured_hotkey() -> Hotkey:
    """Phase 2: from GPUCC_HOTKEY or the default. Persistent settings arrive in phase 3."""
    text = os.environ.get("GPUCC_HOTKEY", DEFAULT_HOTKEY)
    try:
        return parse_hotkey(text)
    except ValueError:
        log.warning("invalid GPUCC_HOTKEY %r, using default", text)
        return parse_hotkey(DEFAULT_HOTKEY)


def screen_for(origin: tuple[int, int] | None) -> QScreen:
    """Qt 6 keeps each screen's *native* top-left corner → match the physical monitor origin."""
    if origin is not None:
        for s in QGuiApplication.screens():
            if (s.geometry().x(), s.geometry().y()) == origin:
                return s
    cursor_screen = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center())
    return cursor_screen or QGuiApplication.primaryScreen()


def should_follow(current: TargetApp | None, new: TargetApp | None) -> bool:
    """A pinned overlay switches to ``new`` unless it is no app (shell/overlay) or the same process."""
    return new is not None and (current is None or new.pid != current.pid)


def migrate_autostart(current: AutostartEntry, legacy: AutostartEntry, command: str) -> bool:
    """Carry an enabled autostart over from the former product name (never enables it on its own)."""
    if not legacy.command():
        return False
    try:
        if not current.command():
            current.enable(command)
        legacy.disable()
    except OSError:
        log.exception("autostart migration failed")
        return False
    return True


def autostart_command() -> str:
    """Windowless start of this installation (SetWhichGPU.exe, or pythonw -m gpucc from source)."""
    return self_command_line()


def refresh_autostart(entry: AutostartEntry, command: str) -> bool:
    """An enabled autostart that points to another location (moved/re-installed) is updated to ``command``."""
    current = entry.command()
    if not current or current == command:
        return False
    try:
        entry.enable(command)
    except OSError:
        log.exception("autostart update failed")
        return False
    return True


def restart_command() -> list[str]:
    """New instance that waits until this one has released the single-instance lock."""
    return self_command(RESTART_FLAG)


class Controller(QObject):
    def __init__(
        self,
        app: QApplication,
        *,
        discovery: GpuDiscovery,
        probe: ForegroundProbe,
        preferences: PreferenceRegistry,
        hotkey: Hotkey,
        store: ProfileStore,
        autostart: AutostartEntry | None = None,
    ) -> None:
        super().__init__()
        self._app = app
        self._discovery_service = discovery
        self._probe = probe
        self._preferences = preferences
        self._hotkey = hotkey
        self._store = store
        self._assignment = AssignmentService(preferences, store)
        self._autostart = autostart
        self._discovery: DiscoveryResult = discovery.scan()
        self._history: deque[GpuSnapshot] = deque(maxlen=HISTORY_LENGTH)
        self._target: TargetApp | None = None
        self._target_pids: frozenset[int] = frozenset()
        self._preferred: PreferredGpu | None = None
        self._last_change_at: float | None = None
        self._snapshots_since_tree = 0
        self._manual = False  # target picked from the side panel → pinned follow paused
        self._last_foreground_hwnd = 0
        self._app_targets: dict[str, TargetApp] = {}
        self._snapshots_since_list = 0
        # Local AI runtimes (ADR-0003): opt-in, only queried while the overlay shows such a runtime.
        # On unless switched off in the tray menu ("" was the "off" value of early builds).
        self._localai_enabled = store.get_setting(LOCALAI_SETTING) in (None, "1")
        self._ai_report: ModelReport | None = None
        self._snapshots_since_ai = 0
        self.localai = LocalAiThread()
        self.localai.report_ready.connect(self._on_ai_report)

        self.library = LibraryService(
            lambda: self._store.settings_with_prefix(LEARNED_PREFIX),
            prewarm=getattr(probe, "prewarm", None),  # version info read off the UI thread
            extra_paths=self._known_exe_paths,
        )
        self.library.games_ready.connect(self._on_games_ready)

        self.overlay = OverlayWindow()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.apply_requested.connect(self.apply_choice)
        self.overlay.app_selected.connect(self.select_app)
        self.overlay.follow_requested.connect(self.resume_follow)
        self.overlay.rescan_requested.connect(self.rescan_library)
        self.overlay.program_chosen.connect(self.add_program)
        self.overlay.custom_remove_requested.connect(self.remove_program)
        self.overlay.apps_panel_toggled.connect(self._on_apps_panel_toggled)
        self.hotkeys = HotkeyService()
        app.installNativeEventFilter(self.hotkeys.native_filter)
        self.hotkeys.hotkey_pressed.connect(self.toggle_overlay)
        self.hotkeys.show_requested.connect(self.open_overlay)
        self.hotkeys.quit_requested.connect(self.quit)
        self.hotkeys.hardware_changed.connect(self.rescan)
        self.tray = TrayService(
            str(hotkey),
            autostart_available=autostart is not None,
            language=store.get_setting(LANGUAGE_SETTING, SYSTEM) or SYSTEM,
            localai=self._localai_enabled,
        )
        self.tray.language_chosen.connect(self.set_language_choice)
        self.tray.localai_toggled.connect(self.set_localai)
        self.tray.open_overlay.connect(self.open_overlay)
        self.tray.rescan.connect(self.rescan)
        self.tray.rescan.connect(self.rescan_library)
        self.tray.autostart_toggled.connect(self.set_autostart)
        self.tray.revert_requested.connect(self.revert_all)
        self.tray.set_autostart_checked(bool(autostart and autostart.command()))
        self.tray.open_logs.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir()))))
        self.tray.quit_requested.connect(self.quit)
        self.monitoring = MonitoringThread(default_sampler, self._discovery.gpus)
        self.monitoring.worker.snapshot_ready.connect(self._on_snapshot)

        # Pinned overlay follows the foreground app (event driven, debounced for Alt+Tab).
        self._follow_timer = QTimer(self)
        self._follow_timer.setSingleShot(True)
        self._follow_timer.setInterval(FOLLOW_DEBOUNCE_MS)
        self._follow_timer.timeout.connect(self._follow_foreground)
        self._foreground_hook = user32.ForegroundHook(self._on_foreground_event)
        self.overlay.pinned_changed.connect(self._on_pinned_changed)

        # Game mode (ADR-0002)
        self.gamemode = GameModeService(store, data_dir() / "gamemode")
        self.gamemode.status_changed.connect(self._on_gamemode_status)
        self.overlay.gamemode_requested.connect(self.start_gamemode)
        self.tray.gamemode_stop.connect(self.gamemode.request_stop)

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self.monitoring.start()
        self.library.rescan()
        self.tray.show()
        QTimer.singleShot(0, self._recover_gamemode)
        err = self.hotkeys.register(self._hotkey)
        if err:
            reason = (
                tr("already taken by another application")
                if err == ERROR_HOTKEY_ALREADY_REGISTERED
                else tr("error {code}", code=err)
            )
            self.tray.notify(
                tr("Hotkey not available"),
                tr("{hotkey} is {reason}. Open the overlay via the tray icon.", hotkey=self._hotkey, reason=reason),
                True,
            )
        log.info("started", extra={"fields": {"gpus": len(self._discovery.gpus), "hotkey": str(self._hotkey)}})

    def quit(self) -> None:
        log.info("quitting")
        if self.gamemode.active:
            self.gamemode.request_stop()  # the helper re-enables the GPU on its own
        self._foreground_hook.stop()
        self.hotkeys.unregister()
        self.overlay.hide()
        self.tray.hide()
        self.monitoring.shutdown()
        self.localai.shutdown()
        self._store.close()
        self._app.quit()

    def set_language_choice(self, choice: str) -> None:
        """Persist the language; switching needs a restart because all widgets are built translated."""
        self._store.set_setting(LANGUAGE_SETTING, choice)
        new = resolve_language(choice, user32.ui_language_id())
        log.info("language chosen", extra={"fields": {"choice": choice, "effective": new}})
        if new == language():
            return
        if self.gamemode.active:  # a restart would end the running game mode session
            self.tray.notify(APP_NAME, tr("The new language is used after the next start."))
            return
        self.restart()

    def set_localai(self, enabled: bool) -> None:
        self._localai_enabled = enabled
        self._store.set_setting(LOCALAI_SETTING, "1" if enabled else "0")
        log.info("local AI models", extra={"fields": {"enabled": enabled}})
        self._ai_report = None
        if self.overlay.isVisible():
            self._query_localai(force=True)
            self._render()

    def _ai_runtime(self) -> str | None:
        t = self._target
        runtime = runtime_for(t.exe_path) if t is not None and t.running and t.exe_path else None
        return runtime.name if runtime else None

    def _query_localai(self, force: bool = False) -> None:
        """Only while enabled, the overlay is open and its target *is* Ollama / LM Studio."""
        runtime = self._ai_runtime()
        if not (self._localai_enabled and runtime):
            return
        self._snapshots_since_ai += 1
        if force or self._snapshots_since_ai >= LOCALAI_EVERY:
            self._snapshots_since_ai = 0
            self.localai.request(runtime)

    def _on_ai_report(self, report: object) -> None:
        if isinstance(report, ModelReport):
            self._ai_report = report
            if self.overlay.isVisible():
                self._render()

    def restart(self) -> None:
        import subprocess

        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(restart_command(), creationflags=flags, close_fds=True)
        except OSError:
            log.exception("restart failed")
            self.tray.notify(APP_NAME, tr("The new language is used after the next start."), True)
            return
        self.quit()

    # ------------------------------------------------------------------ overlay
    def toggle_overlay(self) -> None:
        if not self.overlay.isVisible():
            self.open_overlay()
            return
        if self.overlay.pinned and not self.overlay.isActiveWindow():
            # Pinned overlay + hotkey in another app → follow that app instead of closing.
            target = self._probe.capture()
            if should_follow(self._target, target):
                self._manual = False
                self._set_target(target)
                self._render()
                self._refresh_app_list()
                return
        self.overlay.dismiss("hotkey")

    def _on_foreground_event(self, hwnd: int) -> None:
        self._last_foreground_hwnd = hwnd
        self._follow_timer.start()

    def _on_pinned_changed(self, pinned: bool) -> None:
        if pinned:
            ok = self._foreground_hook.start()
            log.info("follow foreground", extra={"fields": {"hook": ok}})
        else:
            self._foreground_hook.stop()
            self._follow_timer.stop()

    def _follow_foreground(self) -> None:
        if not (self.overlay.isVisible() and self.overlay.pinned) or self._manual:
            return
        target = self._probe.capture()  # None for desktop/taskbar/our own overlay → keep current
        if should_follow(self._target, target):
            log.info("pinned overlay follows", extra={"fields": {"pid": target.pid if target else None}})
            self._set_target(target)
            self._render()
            self._refresh_app_list()

    # ------------------------------------------------------------------ side panel
    def select_app(self, key: str) -> None:
        """User picked an application in the side panel → show it, pause pinned follow."""
        target = self._app_targets.get(key)
        if target is None:
            return
        if target.hwnd:  # refresh window data; fall back to the listed snapshot if it just closed
            target = self._probe.capture_window(target.hwnd) or target
        self._manual = True
        self._set_target(target)
        self._render()
        self._refresh_app_list()

    def _on_apps_panel_toggled(self, open_: bool) -> None:
        if open_:
            self.library.ensure_fresh()
            self._update_scan_state()
            if not self.overlay.apps_panel.has_rows:
                # First opening: show the loading animation first, build the list right after it painted.
                self.overlay.apps_panel.set_loading(True)
                QTimer.singleShot(LIST_FIRST_BUILD_DELAY_MS, self._first_list_build)
            else:
                self._refresh_app_list()

    def _first_list_build(self) -> None:
        self._refresh_app_list()

    def _known_exe_paths(self) -> list[str]:
        """Saved preferences, profiles and user-added programs (GUI thread: registry + SQLite)."""
        try:
            saved = list(self._preferences.entries())
        except OSError:
            saved = []
        return [
            *saved,
            *(path for path, _, _ in self._store.profiles()),
            *self._store.settings_with_prefix(CUSTOM_PREFIX).values(),
        ]

    def add_program(self, path: str) -> None:
        """A program the scanners missed, picked by the user. Only remembered – never started."""
        full = valid_program_path(path)
        if full is None:
            self.tray.notify(tr("Program not added"), tr("Please choose an existing program file (.exe)."), True)
            return
        self._store.set_setting(CUSTOM_PREFIX + full.lower(), full)
        log.info("custom program added")
        running = next((t for t in self._probe.running_apps() if t.app_key == full.lower()), None)
        self._manual = True
        self._set_target(running or self._probe.describe_exe(full))
        self.overlay.set_apps_open(True)
        self._render()
        self._refresh_app_list()

    def remove_program(self, key: str) -> None:
        self._store.delete_setting(CUSTOM_PREFIX + key)
        log.info("custom program removed")
        self._refresh_app_list()

    def rescan_library(self) -> None:
        """Explicit refresh after installing/removing games (panel button, F5, tray)."""
        self.library.rescan()
        self._update_scan_state()
        self._refresh_app_list()  # running apps and saved entries refresh immediately

    def _update_scan_state(self) -> None:
        games = self.library.games
        counts = (
            (sum(g.is_game for g in games), sum(not g.is_game for g in games)) if self.library.has_scanned else None
        )
        self.overlay.apps_panel.set_scan_state(self.library.scanning, counts)
        self._update_loading()

    def _update_loading(self) -> None:
        """Spinner while the very first scan runs or before the first list was built."""
        first_scan = self.library.scanning and not self.library.has_scanned
        self.overlay.apps_panel.set_loading(first_scan or not self.overlay.apps_panel.has_rows)

    def _on_games_ready(self, games: object) -> None:
        self.library.accept(games)
        self._update_scan_state()
        if self._target is not None:
            self._target = with_game(self._target, self.library.games)
        self._refresh_app_list()

    def _learn_game_exes(self, apps: list[TargetApp], latest: GpuSnapshot | None) -> None:
        """Remember which exe of an installed game actually used the GPU (launcher ≠ game)."""
        if latest is None or not self.library.games:
            return
        using = {p.pid for p in latest.processes if p.dedicated_bytes >= LEARN_MIN_VRAM or any(p.engines.values())}
        exes = [a.exe_path for a in apps if a.exe_path and a.pid in using]
        learned = learn_render_exes(self.library.games, exes)
        for key, exe in learned.items():
            self._store.set_setting(LEARNED_PREFIX + key, exe)
            log.info("learned game exe", extra={"fields": {"game": key, "exe": exe}})
        if learned:
            self.library.apply_learned(learned)

    def resume_follow(self) -> None:
        self._manual = False
        target = self._probe.capture_window(self._last_foreground_hwnd)
        if target is not None:
            self._set_target(target)
            self._render()
        self._refresh_app_list()

    def _refresh_app_list(self) -> None:
        if not (self.overlay.isVisible() and self.overlay.apps_open):
            return
        latest = self._history[-1] if self._history else None
        running = self._probe.running_apps()
        background = self._probe.background_apps(background_candidates(latest), exclude={t.pid for t in running})
        self._learn_game_exes([*running, *background], latest)
        rows, targets = build_app_list(
            games=self.library.games,
            running=running,
            background=background,
            saved_values=self._preferences.entries(),
            profile_paths=[path for path, _, _ in self._store.profiles()],
            describe_exe=self._probe.describe_exe,
            discovery=self._discovery,
            history=list(self._history),
            parents=self._probe.parent_map(),
            custom_paths=list(self._store.settings_with_prefix(CUSTOM_PREFIX).values()),
        )
        self._app_targets = targets
        current = self._target.app_key if self._target else None
        self.overlay.set_app_list(rows, current, following=not self._manual)
        self._update_loading()

    def _target_alive(self) -> bool:
        t = self._target
        if t is None or not t.running:
            return True  # nothing to report for "not running" entries
        if t.hwnd:
            return user32.is_window(t.hwnd)
        return process.creation_time(t.pid) is not None

    def open_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.raise_()
            self.overlay.activateWindow()
            return
        target = self._probe.capture()  # before we take focus
        if target is not None and target.fullscreen is FullscreenState.EXCLUSIVE:
            self.tray.notify(
                tr("Overlay not available in exclusive fullscreen"),
                tr("{app} is running in exclusive fullscreen.", app=target.display_name),
            )
            return
        self._manual = False
        self._last_foreground_hwnd = target.hwnd if target else 0
        self._set_target(target)
        self._render()
        self.overlay.show_on(screen_for(target.monitor_origin if target else None))
        self._refresh_app_list()
        user32.set_foreground(int(self.overlay.winId()))
        self.monitoring.request_interval.emit(INTERVAL_ACTIVE_MS)
        self.monitoring.request_sample.emit()

    def _set_target(self, target: TargetApp | None) -> None:
        if target is not None:
            target = with_game(target, self.library.games)
        self._target = target
        self._target_pids = self._probe.process_tree(target.pid) if target else frozenset()
        self._snapshots_since_tree = 0
        raw = self._preferences.read(target.exe_path) if target and target.exe_path else None
        self._preferred = interpret(raw, self._discovery) if target else None
        self._last_change_at = self._assignment.last_change_at(target.exe_path) if target and target.exe_path else None
        runtime = self._ai_runtime()
        if self._ai_report is not None and self._ai_report.runtime != runtime:
            self._ai_report = None  # never show another runtime's answer
        self._query_localai(force=True)

    # ------------------------------------------------------------------ assignment
    def apply_choice(self, choice: object) -> None:
        """Write the Windows preference for the current target (explicit user action only)."""
        target = self._target
        if target is None or not target.exe_path:
            return
        key = choice if isinstance(choice, GpuKey) else None
        support = support_for(target, key, self._discovery)
        if not support.supported:
            self.tray.notify(tr("GPU assignment not possible"), support.reason, True)
            return
        try:
            self._assignment.apply(target.exe_path, target.display_name, key)
        except OSError as e:
            self.tray.notify(tr("Saving failed"), str(e), True)
            return
        self._set_target(target)  # re-read registry value and change time
        self.overlay.mark_applied()
        self._render()
        self._refresh_app_list()

    # ------------------------------------------------------------------ game mode (ADR-0002)
    def start_gamemode(self, key: object) -> None:
        target = self._target
        gpu = self._discovery.by_key(key) if isinstance(key, GpuKey) else None
        if target is None or gpu is None:
            return
        check = preflight(
            gpu=gpu,
            discovery=self._discovery,
            snapshot=self._history[-1] if self._history else None,
            process_name=target.exe_name if target.exe_path else None,
            game_pids=self._target_pids,
            session_active=self.gamemode.active,
        )
        if not check.ok:
            QMessageBox.warning(None, tr("Game mode not possible"), "\n".join(f"• {b}" for b in check.blockers))
            return
        text = tr(
            "{app} ignores the Windows GPU preference. Game mode temporarily disables {gpu} so the game "
            "has to use another GPU.\n\n"
            "1. Confirm the Windows administrator prompt.\n"
            "2. Close {app} if it is running – {gpu} is then disabled.\n"
            "3. Start {app} again.\n"
            "4. When you exit the game, {gpu} is enabled again automatically.\n\n"
            "While game mode is active, {gpu} is unavailable for everything else (e.g. CUDA, Blender, "
            "NVIDIA overlay). You can end it at any time from the tray menu.",
            app=target.display_name,
            gpu=gpu.short_name,
        )
        if check.warnings:
            text += "\n\n" + "\n".join(f"⚠ {w}" for w in check.warnings)
        answer = QMessageBox.question(None, tr("Start game mode?"), text)
        if answer != QMessageBox.StandardButton.Yes:
            return
        error = self.gamemode.start(Session(gpu.instance_id, gpu.short_name, target.exe_name, target.display_name))
        if error == "cancelled":
            self.tray.notify(tr("Game mode not started"), tr("The administrator prompt was declined."))
        elif error:
            self.tray.notify(tr("Game mode not started"), error, True)

    def _on_gamemode_status(self, status: object) -> None:
        if not isinstance(status, GameModeStatus):
            return
        s = status.session
        messages = {
            Phase.WAITING_FOR_EXIT: (tr("Game mode"), tr("Close {app} – then {gpu} will be disabled.")),
            Phase.DISABLED: (tr("Game mode active"), tr("{gpu} is disabled – start {app} now.")),
            Phase.RESTORED: (tr("Game mode ended"), tr("{gpu} is enabled again.")),
            Phase.TIMEOUT: (tr("Game mode ended"), tr("{app} was not started in time – {gpu} is enabled again.")),
        }
        if status.phase is Phase.FAILED:
            self.tray.notify(tr("Game mode failed"), status.detail, True)
        elif status.phase in messages:
            title, body = messages[status.phase]
            self.tray.notify(title, body.format(app=s.app_name, gpu=s.gpu_name))
        active = status.phase not in FINAL_PHASES
        self.tray.set_gamemode(tr("End game mode – re-enable {gpu}", gpu=s.gpu_name) if active else None)
        if self.overlay.isVisible():
            self._render()

    def _gamemode_note(self) -> str | None:
        status = self.gamemode.status
        if status is None or status.phase in FINAL_PHASES:
            return None
        s = status.session
        notes = {
            Phase.STARTING: tr("Game mode: waiting for the administrator prompt …"),
            Phase.WAITING_FOR_EXIT: tr("Game mode: close {app} – then {gpu} will be disabled."),
            Phase.DISABLED: tr("Game mode: {gpu} is disabled – start {app} now."),
            Phase.RUNNING: tr("Game mode active: {gpu} is disabled until {app} exits."),
        }
        template = notes.get(status.phase)
        return template.format(app=s.app_name, gpu=s.gpu_name) if template else None

    def _recover_gamemode(self) -> None:
        session = self.gamemode.pending_recovery()
        if session is None:
            return
        answer = QMessageBox.question(
            None,
            tr("GPU still disabled"),
            tr(
                "{gpu} is still disabled from a previous game mode session ({app}). Enable it again now?\n\n"
                "Alternatively: Device Manager → Display adapters → {gpu} → Enable device.",
                gpu=session.gpu_name,
                app=session.app_name,
            ),
        )
        if answer == QMessageBox.StandardButton.Yes:
            error = self.gamemode.reenable(session)
            if error:
                self.tray.notify(tr("GPU still disabled"), error, True)

    def revert_all(self) -> None:
        changed = {e.exe_path.lower() for e in self._store.journal() if e.status == "applied"}
        if not changed:
            self.tray.notify(tr("Nothing to reset"), tr("SetWhichGPU has not changed any preferences yet."))
            return
        answer = QMessageBox.question(
            None,
            tr("Reset GPU preferences"),
            tr(
                "Reset all GPU preferences changed by SetWhichGPU ({count} application(s)) "
                "to their original state?\n\nEntries that were changed elsewhere in the meantime stay untouched.",
                count=len(changed),
            ),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        report = self._assignment.revert_all()
        text = tr("{n} reset", n=len(report.reverted))
        if report.conflicts:
            text += tr(", {n} changed elsewhere (left untouched)", n=len(report.conflicts))
        if report.failed:
            text += tr(", {n} failed", n=len(report.failed))
        self.tray.notify(tr("GPU preferences reset"), text + tr(". Takes effect after restarting the applications."))
        if self.overlay.isVisible() and self._target is not None:
            self._set_target(self._target)
            self._render()

    def set_autostart(self, enabled: bool) -> None:
        if self._autostart is None:
            return
        try:
            if enabled:
                self._autostart.enable(autostart_command())
            else:
                self._autostart.disable()
        except OSError as e:
            self.tray.notify(tr("Could not change autostart"), str(e), True)
        actual = bool(self._autostart.command())
        self.tray.set_autostart_checked(actual)
        log.info("autostart", extra={"fields": {"enabled": actual}})

    def _on_overlay_closed(self, reason: str) -> None:
        self.monitoring.request_interval.emit(INTERVAL_IDLE_MS)
        target = self._target
        # On focus loss the user clicked elsewhere – never steal focus back.
        restore = target is not None and reason != "focus_lost" and bool(target.hwnd) and user32.is_window(target.hwnd)
        if restore and target is not None and not user32.set_foreground(target.hwnd):
            log.info("focus not restored (elevated target?)", extra={"fields": {"pid": target.pid}})
        self._target = None
        self._manual = False

    def _render(self) -> None:
        target = self._target
        observed = observe(self._target_pids, self._history) if target else None
        state = build_state(
            target=target,
            discovery=self._discovery,
            snapshot=self._history[-1] if self._history else None,
            observed=observed,
            preferred=self._preferred,
            hotkey_text=str(self._hotkey),
            target_running=self._target_alive(),
            last_change_at=self._last_change_at,
            gamemode_note=self._gamemode_note(),
            ai_runtime=self._ai_runtime(),
            ai_enabled=self._localai_enabled,
            ai_report=self._ai_report,
            history=self._history,
            target_pids=self._target_pids,
        )
        self.overlay.apply_state(state)

    def _on_snapshot(self, snapshot: object) -> None:
        if isinstance(snapshot, GpuSnapshot):
            self._history.append(snapshot)
            if self.overlay.isVisible():
                self._refresh_process_tree()
                self._query_localai()
                self._render()
                self._snapshots_since_list += 1
                if self._snapshots_since_list >= LIST_REFRESH_EVERY:
                    self._snapshots_since_list = 0
                    self._refresh_app_list()

    def _refresh_process_tree(self) -> None:
        """While pinned, apps may spawn workers (e.g. Blender render, Unity import workers)."""
        self._snapshots_since_tree += 1
        if self._target is not None and self._snapshots_since_tree >= TREE_REFRESH_EVERY:
            self._snapshots_since_tree = 0
            self._target_pids = self._probe.process_tree(self._target.pid)

    # ------------------------------------------------------------------ hardware
    def rescan(self) -> None:
        try:
            self._discovery = self._discovery_service.scan()
        except Exception:
            log.exception("rescan failed")
            return
        self._history.clear()
        self.monitoring.request_rebind.emit(self._discovery.gpus)
