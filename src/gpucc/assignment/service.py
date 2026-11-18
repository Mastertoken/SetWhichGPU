"""Applying and reverting per-app GPU preferences – journaled, reversible, HKCU only.

Rules (AGENTS.md §4): journal entry *before* writing, only touch our two fields, never
overwrite a value that was changed outside SetWhichGPU during a revert.
"""

from __future__ import annotations

import logging
import time

from gpucc.assignment.win_pref import compose
from gpucc.core.models import ApplyResult, GpuKey, RevertReport
from gpucc.core.ports import PreferenceRegistry
from gpucc.profiles.store import ProfileStore

log = logging.getLogger(__name__)


class AssignmentService:
    def __init__(self, registry: PreferenceRegistry, store: ProfileStore) -> None:
        self._registry = registry
        self._store = store

    def apply(self, exe_path: str, display_name: str, choice: GpuKey | None, trigger: str = "overlay") -> ApplyResult:
        old = self._registry.read(exe_path)
        new = compose(old, choice)
        now = time.time()
        self._store.upsert_profile(exe_path, display_name, choice)
        if new == old:
            return ApplyResult(False, old, new, None, now)
        entry = self._store.journal_begin(exe_path, old, new, trigger)
        try:
            if new is None:
                self._registry.delete(exe_path)
            else:
                self._registry.write(exe_path, new)
        except OSError as e:
            self._store.journal_finish(entry, "failed", str(e))
            log.exception("writing GPU preference failed", extra={"fields": {"exe": exe_path}})
            raise
        self._store.journal_finish(entry, "applied")
        log.info(
            "gpu preference applied",
            extra={"fields": {"exe": exe_path, "old": old, "new": new, "trigger": trigger}},
        )
        return ApplyResult(True, old, new, entry, now)

    def last_change_at(self, exe_path: str) -> float | None:
        entry = self._store.last_applied(exe_path)
        return entry.ts if entry else None

    def revert_all(self) -> RevertReport:
        """Restore every value SetWhichGPU changed to its state before our first change."""
        reverted: list[str] = []
        conflicts: list[str] = []
        failed: list[str] = []
        by_exe: dict[str, list[tuple[str | None, str | None]]] = {}
        for e in self._store.journal():
            if e.status == "applied":
                by_exe.setdefault(e.exe_path.lower(), []).append((e.old_value, e.new_value))
        exe_names = {e.exe_path.lower(): e.exe_path for e in self._store.journal()}
        for low, changes in by_exe.items():
            exe = exe_names[low]
            original, last_written = changes[0][0], changes[-1][1]
            current = self._registry.read(exe)
            if current == original:
                continue
            if current != last_written:
                conflicts.append(exe)
                entry = self._store.journal_begin(exe, current, original, "revert")
                self._store.journal_finish(entry, "skipped", "changed outside SetWhichGPU")
                continue
            entry = self._store.journal_begin(exe, current, original, "revert")
            try:
                if original is None:
                    self._registry.delete(exe)
                else:
                    self._registry.write(exe, original)
            except OSError as e:
                self._store.journal_finish(entry, "failed", str(e))
                failed.append(exe)
                continue
            self._store.journal_finish(entry, "applied")
            reverted.append(exe)
        log.info(
            "revert all",
            extra={"fields": {"reverted": reverted, "conflicts": conflicts, "failed": failed}},
        )
        return RevertReport(tuple(reverted), tuple(conflicts), tuple(failed))
