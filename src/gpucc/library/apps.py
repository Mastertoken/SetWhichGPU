"""Installed programs from the Start Menu (all users + current user), read-only."""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from gpucc.i18n import tr
from gpucc.library.exe_resolver import LAUNCHER_EXE, SKIP_EXE
from gpucc.library.models import ExeSource, InstalledGame

log = logging.getLogger(__name__)

START_MENU_DIRS = (
    Path(os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")),
    Path(os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")),
)
WINDOWS_DIR = os.path.expandvars(r"%WINDIR%").lower() + "\\"
#: Shortcut names that are never "the application".
SKIP_NAME = re.compile(r"(?i)(uninstall|deinstall|readme|help|manual|handbuch|release notes|website|license)")
_SQUIRREL_APP_DIR = re.compile(r"^app-(\d+(?:\.\d+)*)$")


def _version_key(name: str) -> tuple[int, ...]:
    m = _SQUIRREL_APP_DIR.match(name)
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def resolve_app_exe(target: Path) -> tuple[Path, ExeSource, str | None]:
    """Shortcut target → executable that actually runs (launcher/stub aware)."""
    folder = target.parent
    # Squirrel apps (Discord, Slack …): root stub + Update.exe + versioned app-x.y.z folders.
    if (folder / "Update.exe").is_file():
        versions = sorted(
            (d for d in folder.iterdir() if d.is_dir() and _SQUIRREL_APP_DIR.match(d.name)),
            key=lambda d: _version_key(d.name),
        )
        if versions and (versions[-1] / target.name).is_file():
            note = tr("The path contains the program version and changes with updates.")
            return versions[-1] / target.name, ExeSource.GUESSED, note
    # Launchers next to the real program (blender-launcher.exe → blender.exe).
    if LAUNCHER_EXE.search(target.stem):
        siblings = [
            p
            for p in folder.glob("*.exe")
            if p != target and not SKIP_EXE.search(p.name) and not LAUNCHER_EXE.search(p.stem)
        ]
        if siblings:
            best = max(siblings, key=lambda p: p.stat().st_size)
            note = tr("Starts via {launcher}; the preference applies to {exe}.", launcher=target.name, exe=best.name)
            return best, ExeSource.GUESSED, note
    return target, ExeSource.LAUNCHER, None


def scan_start_menu(
    resolve_shortcut: Callable[[str], str | None],
    skip_dirs: Iterable[str] = (),
    menu_dirs: Iterable[Path] = START_MENU_DIRS,
) -> list[InstalledGame]:
    skip = tuple(d.lower().rstrip("\\") + "\\" for d in skip_dirs)
    found: dict[str, InstalledGame] = {}
    for root in menu_dirs:
        if not root.is_dir():
            continue
        for lnk in sorted(root.rglob("*.lnk")):
            name = lnk.stem
            if SKIP_NAME.search(name):
                continue
            target = resolve_shortcut(str(lnk))
            if not target or not target.lower().endswith(".exe"):
                continue
            low = target.lower()
            if low.startswith(WINDOWS_DIR) or low.startswith(skip) or SKIP_EXE.search(Path(target).name):
                continue
            tpath = Path(target)
            if not tpath.is_file():
                continue
            exe, source, note = resolve_app_exe(tpath)
            key = str(exe).lower()
            if key in found and len(found[key].name) <= len(name):
                continue  # several shortcuts → keep the shortest (usually the main) name
            found[key] = InstalledGame("StartMenu", key, name, str(exe.parent), str(exe), source, kind="app", note=note)
    return sorted(found.values(), key=lambda a: a.name.lower())
