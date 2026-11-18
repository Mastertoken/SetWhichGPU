"""Application data locations. ``GPUCC_DATA_DIR`` overrides (e.g. one per git worktree)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from gpucc.branding import APP_NAME, LEGACY_DATA_DIR

APP_DIR_NAME = APP_NAME


def migrate_legacy_dir(new: Path, legacy: Path) -> bool:
    """Move the former data folder (profiles, change journal, logs) to the new name once."""
    if new.exists() or not legacy.is_dir():
        return False
    try:
        legacy.rename(new)
    except OSError:  # e.g. a file is still open → copy instead, keep the original
        shutil.copytree(legacy, new)
    return True


def data_dir() -> Path:
    override = os.environ.get("GPUCC_DATA_DIR")
    if override:
        base = Path(override)
    else:
        local = Path(os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"))
        base = local / APP_DIR_NAME
        migrate_legacy_dir(base, local / LEGACY_DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base


def log_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
