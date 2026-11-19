"""Background library scanning for the Qt UI (results delivered via a queued signal)."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from gpucc.library.models import ExeSource, InstalledGame
from gpucc.library.scanner import scan_all

log = logging.getLogger(__name__)

RESCAN_AFTER_S = 600


class LibraryService(QObject):
    games_ready = Signal(object)  # list[InstalledGame]; emitted from the worker thread → queued

    def __init__(
        self,
        learned_provider: Callable[[], Mapping[str, str]],
        prewarm: Callable[[Iterable[str]], None] | None = None,
        extra_paths: Callable[[], Iterable[str]] | None = None,
    ) -> None:
        """``prewarm`` runs on the worker thread after the scan with all game/program exes plus
        ``extra_paths()`` (saved preferences, user-added programs – read on the GUI thread)."""
        super().__init__()
        self._learned = learned_provider
        self._prewarm = prewarm
        self._extra_paths = extra_paths
        self._games: list[InstalledGame] = []
        self._scanned_at = 0.0
        self._running = False
        self._lock = threading.Lock()

    @property
    def games(self) -> list[InstalledGame]:
        return self._games

    @property
    def scanning(self) -> bool:
        return self._running

    @property
    def has_scanned(self) -> bool:
        return self._scanned_at > 0

    def ensure_fresh(self) -> None:
        if time.monotonic() - self._scanned_at > RESCAN_AFTER_S:
            self.rescan()

    def rescan(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
        learned = dict(self._learned())  # read on the GUI thread (SQLite connection lives there)
        extra = list(self._extra_paths()) if self._extra_paths else []
        threading.Thread(target=self._scan, args=(learned, extra), name="gpucc-library", daemon=True).start()

    def _scan(self, learned: dict[str, str], extra: list[str]) -> None:
        games: list[InstalledGame] = []
        try:
            games = scan_all(learned)
            if self._prewarm is not None:
                self._prewarm([*(g.exe_path for g in games if g.exe_path), *extra])
        except Exception:
            log.exception("library scan failed")
        finally:
            with self._lock:
                self._running = False
        self.games_ready.emit(games)

    def apply_learned(self, learned: Mapping[str, str]) -> None:
        """Update in-memory games with newly learned render executables (GUI thread)."""
        self._games = [
            replace(g, exe_path=learned[g.key], exe_source=ExeSource.LEARNED) if g.key in learned else g
            for g in self._games
        ]

    def accept(self, games: object) -> None:
        """Slot for games_ready on the GUI thread."""
        if isinstance(games, list):
            self._games = games
            self._scanned_at = time.monotonic()
