"""SQLite store: profiles (user intent), change journal and settings.

Schema changes are append-only migrations; ``schema_version`` records the applied level.
Used from the GUI thread only.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from gpucc.core.models import GpuKey, JournalEntry

MIGRATIONS: tuple[str, ...] = (
    # 1 – initial schema
    """
    CREATE TABLE profiles (
        exe_path     TEXT PRIMARY KEY COLLATE NOCASE,
        display_name TEXT NOT NULL,
        gpu_key      TEXT,             -- NULL = Windows decides
        created_at   REAL NOT NULL,
        updated_at   REAL NOT NULL
    );
    CREATE TABLE change_journal (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        ts        REAL NOT NULL,
        exe_path  TEXT NOT NULL COLLATE NOCASE,
        old_value TEXT,
        new_value TEXT,
        trigger   TEXT NOT NULL,
        status    TEXT NOT NULL,
        detail    TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX ix_journal_exe ON change_journal (exe_path, id);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
)


class ProfileStore:
    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(str(path), isolation_level=None)  # autocommit; explicit txns below
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ------------------------------------------------------------------ schema
    def _migrate(self) -> None:
        self._db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        row = self._db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = int(row[0] or 0)
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            self._db.execute("BEGIN")
            try:
                for statement in filter(str.strip, script.split(";")):
                    self._db.execute(statement)
                self._db.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    @property
    def schema_version(self) -> int:
        return int(self._db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0)

    # ------------------------------------------------------------------ profiles
    def upsert_profile(self, exe_path: str, display_name: str, gpu_key: GpuKey | None) -> None:
        now = time.time()
        self._db.execute(
            """INSERT INTO profiles (exe_path, display_name, gpu_key, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(exe_path) DO UPDATE SET
                 display_name = excluded.display_name, gpu_key = excluded.gpu_key,
                 updated_at = excluded.updated_at""",
            (exe_path, display_name, str(gpu_key) if gpu_key else None, now, now),
        )

    def profile_gpu(self, exe_path: str) -> tuple[bool, GpuKey | None]:
        """(profile exists, intended GPU or None for Windows default)."""
        row = self._db.execute("SELECT gpu_key FROM profiles WHERE exe_path = ?", (exe_path,)).fetchone()
        if row is None:
            return False, None
        return True, GpuKey.parse(row["gpu_key"]) if row["gpu_key"] else None

    def profiles(self) -> list[tuple[str, str, GpuKey | None]]:
        rows = self._db.execute("SELECT exe_path, display_name, gpu_key FROM profiles ORDER BY display_name")
        return [(r["exe_path"], r["display_name"], GpuKey.parse(r["gpu_key"]) if r["gpu_key"] else None) for r in rows]

    # ------------------------------------------------------------------ journal
    def journal_begin(self, exe_path: str, old: str | None, new: str | None, trigger: str) -> int:
        cur = self._db.execute(
            "INSERT INTO change_journal (ts, exe_path, old_value, new_value, trigger, status) VALUES (?,?,?,?,?,?)",
            (time.time(), exe_path, old, new, trigger, "pending"),
        )
        return int(cur.lastrowid or 0)

    def journal_finish(self, entry_id: int, status: str, detail: str = "") -> None:
        self._db.execute("UPDATE change_journal SET status = ?, detail = ? WHERE id = ?", (status, detail, entry_id))

    def journal(self, exe_path: str | None = None) -> list[JournalEntry]:
        if exe_path is None:
            rows = self._db.execute("SELECT * FROM change_journal ORDER BY id")
        else:
            rows = self._db.execute("SELECT * FROM change_journal WHERE exe_path = ? ORDER BY id", (exe_path,))
        return [
            JournalEntry(
                r["id"], r["ts"], r["exe_path"], r["old_value"], r["new_value"], r["trigger"], r["status"], r["detail"]
            )
            for r in rows
        ]

    def last_applied(self, exe_path: str) -> JournalEntry | None:
        applied = [e for e in self.journal(exe_path) if e.status == "applied"]
        return applied[-1] if applied else None

    # ------------------------------------------------------------------ settings
    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def settings_with_prefix(self, prefix: str) -> dict[str, str]:
        rows = self._db.execute("SELECT key, value FROM settings WHERE substr(key, 1, ?) = ?", (len(prefix), prefix))
        return {str(r["key"])[len(prefix) :]: str(r["value"]) for r in rows}

    def close(self) -> None:
        self._db.close()
