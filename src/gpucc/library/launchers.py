"""More game launchers: Epic Games Launcher v2 (per-user, 2026+) and Meta Horizon Link / Oculus (read-only).

The launchers' files are treated as untrusted input: sizes are capped, only the expected fields are read,
and a launch executable must stay inside its game folder (no absolute paths, no ``..``). Nothing is ever
executed – the executable is only used to look up and set the Windows GPU preference.
"""

from __future__ import annotations

import json
import logging
import os
import re
import winreg
from collections.abc import Iterable, Mapping
from pathlib import Path, PureWindowsPath

from gpucc.i18n import tr
from gpucc.library.exe_resolver import resolve_render_exe
from gpucc.library.models import InstalledGame
from gpucc.sanitize import clean_text

log = logging.getLogger(__name__)

MAX_JSONL_BYTES = 16 << 20
MAX_CATALOG_BYTES = 32 << 20
MAX_MANIFEST_BYTES = 1 << 20
MAX_NAME_LEN = 120
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def local_appdata() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def _read_text(path: Path, limit: int) -> str | None:
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_json(path: Path, limit: int) -> object:
    text = _read_text(path, limit)
    if text is None:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError):
        return None


def _str(value: object, limit: int = MAX_NAME_LEN) -> str:
    """Identifiers and paths: control characters removed, otherwise unchanged (display names: clean_text)."""
    return _CONTROL.sub("", value).strip()[:limit] if isinstance(value, str) else ""


def contained(install_dir: Path, relative: str) -> Path | None:
    """``install_dir / relative`` – only if ``relative`` is a plain relative path inside the folder."""
    rel = PureWindowsPath(relative.replace("/", "\\"))
    if not relative or rel.is_absolute() or rel.drive or rel.root or ".." in rel.parts:
        return None
    return install_dir / rel


# ----------------------------------------------------------------------------- Epic Games Launcher v2

EPIC_V2_DIR_NAME = "com.epicgames.eglv2"


def epic_v2_installations(base: Path) -> list[dict[str, object]]:
    """installations.jsonl is an append log (header line, then one JSON object per change): last entry wins."""
    text = _read_text(base / "installations.jsonl", MAX_JSONL_BYTES)
    latest: dict[str, dict[str, object]] = {}
    for line in (text or "").splitlines():
        try:
            entry = json.loads(line)
        except (ValueError, RecursionError):
            continue
        if isinstance(entry, dict) and isinstance(entry.get("installationId"), str):
            latest[entry["installationId"]] = entry
    return [
        e
        for e in latest.values()
        if e.get("complete") is True
        and not e.get("parentInstallationId")  # plug-ins/add-ons of another installation
        and _str(e.get("launchExecutable"), 260)
        and _str(e.get("dir"), 260)
    ]


def epic_v2_titles(base: Path) -> dict[str, str]:
    """itemId → store title from the launcher's catalog cache (missing cache → folder names are used)."""
    data = _read_json(base / "cache" / "prod" / "catalog-cache.json", MAX_CATALOG_BYTES)
    items = data.get("items") if isinstance(data, dict) else None
    titles: dict[str, str] = {}
    for item_id, wrapper in items.items() if isinstance(items, dict) else ():
        item = wrapper.get("item") if isinstance(wrapper, dict) else None
        title = clean_text(item.get("title"), MAX_NAME_LEN) if isinstance(item, dict) else ""
        if title:
            titles[str(item_id)] = title
    return titles


def scan_epic_v2(base: Path, learned: Mapping[str, str]) -> list[InstalledGame]:
    installs = epic_v2_installations(base)
    if not installs:
        return []
    titles = epic_v2_titles(base)
    out = []
    for e in installs:
        install_dir = Path(_str(e.get("dir"), 260))
        launch = contained(install_dir, _str(e.get("launchExecutable"), 260))
        if launch is None or not install_dir.is_dir():
            continue
        game_id = _str(e.get("artifactId")) or _str(e.get("installationId"))
        name = titles.get(_str(e.get("itemId"))) or clean_text(install_dir.name, MAX_NAME_LEN)
        exe, source = resolve_render_exe(install_dir, launch, learned.get(f"epic:{game_id}"))
        out.append(InstalledGame("Epic", game_id, name, str(install_dir), exe, source))
    return out


# ----------------------------------------------------------------------------- Meta Horizon Link / Oculus

OCULUS_KEY = r"Software\Oculus VR, LLC\Oculus"
DEFAULT_META_ROOTS = (Path(r"C:\Program Files\Meta Horizon"), Path(r"C:\Program Files\Oculus"))


def meta_libraries() -> list[Path]:
    """Library folders (each with ``Manifests`` and ``Software``): the default one plus user-added libraries."""
    roots: list[Path] = []
    for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Oculus VR, LLC\Oculus"),):
        try:
            with winreg.OpenKey(hive, key) as k:
                base = str(winreg.QueryValueEx(k, "Base")[0])
                roots.append(Path(base))
        except OSError:
            pass
    libraries = [r / "Software" for r in [*roots, *DEFAULT_META_ROOTS]]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, OCULUS_KEY + r"\Libraries") as libs:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(libs, i)
                except OSError:
                    break
                i += 1
                with winreg.OpenKey(libs, sub) as k:
                    for value in ("OriginalPath", "Path"):
                        try:
                            path = str(winreg.QueryValueEx(k, value)[0])
                        except OSError:
                            continue
                        if path and not path.startswith("\\\\?\\"):  # volume-GUID paths need extra resolving
                            libraries.append(Path(path))
                            break
    except OSError:
        pass
    seen: set[str] = set()
    unique = []
    for lib in libraries:
        if str(lib).lower() not in seen:
            seen.add(str(lib).lower())
            unique.append(lib)
    return unique


def _pretty(canonical: str) -> str:
    return " ".join(w.capitalize() for w in re.split(r"[-_]+", canonical) if w)


def scan_meta(libraries: Iterable[Path], learned: Mapping[str, str]) -> list[InstalledGame]:
    out = []
    for lib in libraries:
        manifests = lib / "Manifests"
        try:
            files = sorted(manifests.glob("*.json")) if manifests.is_dir() else []
        except OSError:
            continue
        for f in files:
            if f.stem.endswith("_assets"):
                continue  # asset packages of another app
            data = _read_json(f, MAX_MANIFEST_BYTES)
            if not isinstance(data, dict) or data.get("isCore") is True:
                continue  # Meta's own runtime components
            canonical = _str(data.get("canonicalName")) or f.stem
            if contained(lib / "Software", canonical) is None:
                continue
            install_dir = lib / "Software" / canonical
            if not install_dir.is_dir():
                continue
            launch_rel = _str(data.get("launchFile"), 260)
            launch = contained(install_dir, launch_rel) if launch_rel else None
            game_id = _str(data.get("appId")) or canonical
            exe, source = resolve_render_exe(install_dir, launch, learned.get(f"meta:{game_id}"))
            name = PureWindowsPath(launch_rel).stem if launch_rel else ""
            if not name or name.lower() in ("game", "launcher", "start", "app"):
                name = _pretty(canonical)
            name = clean_text(name, MAX_NAME_LEN) or canonical
            out.append(
                InstalledGame(
                    "Meta", game_id, name, str(install_dir), exe, source, note=tr("VR game (Meta Horizon Link)")
                )
            )
    return out
