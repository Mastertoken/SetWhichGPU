"""Scan installed games from Steam, Epic, GOG and Meta Horizon (read-only); see launchers.py."""

from __future__ import annotations

import json
import logging
import winreg
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from gpucc.library import steam
from gpucc.library.exe_resolver import resolve_render_exe
from gpucc.library.models import ExeSource, InstalledGame

log = logging.getLogger(__name__)

EPIC_MANIFESTS = Path(r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests")
GOG_KEY = r"SOFTWARE\WOW6432Node\GOG.com\Games"


def steam_root() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            return Path(str(winreg.QueryValueEx(k, "SteamPath")[0]))
    except OSError:
        return None


def scan_steam(root: Path, learned: Mapping[str, str]) -> list[InstalledGame]:
    info = steam.load_appinfo(root)
    games: dict[str, InstalledGame] = {}
    for lib, m in steam.iter_manifests(steam.library_paths(root)):
        appid = m["appid"]
        if appid in steam.NON_GAME_APPIDS or appid in games:
            continue
        install_dir = lib / "steamapps" / "common" / m["installdir"]
        if not install_dir.is_dir():
            continue  # stale manifest (game moved or removed)
        rel = steam.launch_executable(info.get(appid, {}))
        launch = install_dir / rel if rel else None
        key = f"steam:{appid}"
        known = steam.KNOWN_RENDER_EXE.get(appid)
        exe: str | None
        if known and (install_dir / known).is_file() and key not in learned:
            exe, source = str(install_dir / known), ExeSource.LAUNCHER
        else:
            exe, source = resolve_render_exe(install_dir, launch, learned.get(key))
        games[appid] = InstalledGame("Steam", appid, m["name"], str(install_dir), exe, source)
    return list(games.values())


def scan_epic(manifest_dir: Path, learned: Mapping[str, str]) -> list[InstalledGame]:
    out = []
    for f in sorted(manifest_dir.glob("*.item")) if manifest_dir.is_dir() else []:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("bIsIncompleteInstall"):
            continue
        install_dir = Path(str(data.get("InstallLocation", "")))
        if not install_dir.is_dir():
            continue
        rel = str(data.get("LaunchExecutable", ""))
        game_id = str(data.get("AppName") or data.get("CatalogItemId") or f.stem)
        exe, source = resolve_render_exe(
            install_dir, install_dir / rel if rel else None, learned.get(f"epic:{game_id}")
        )
        out.append(InstalledGame("Epic", game_id, str(data.get("DisplayName", game_id)), str(install_dir), exe, source))
    return out


def scan_gog(learned: Mapping[str, str]) -> list[InstalledGame]:
    out: list[InstalledGame] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GOG_KEY)
    except OSError:
        return out
    with root:
        i = 0
        while True:
            try:
                game_id = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, game_id) as k:
                    values = {n: str(winreg.QueryValueEx(k, n)[0]) for n in ("gameName", "exe", "path") if _has(k, n)}
            except OSError:
                continue
            install_dir = Path(values.get("path", ""))
            if not install_dir.is_dir():
                continue
            launch = Path(values["exe"]) if values.get("exe") else None
            exe, source = resolve_render_exe(install_dir, launch, learned.get(f"gog:{game_id}"))
            out.append(InstalledGame("GOG", game_id, values.get("gameName", game_id), str(install_dir), exe, source))
    return out


def _has(key: winreg.HKEYType, name: str) -> bool:
    try:
        winreg.QueryValueEx(key, name)
    except OSError:
        return False
    return True


def scan_all(learned: Mapping[str, str]) -> list[InstalledGame]:
    games: list[InstalledGame] = []
    root = steam_root()
    from gpucc.library import launchers

    scanners: list[tuple[str, Callable[[], list[InstalledGame]]]] = [
        ("steam", lambda: scan_steam(root, learned) if root else []),
        ("epic", lambda: scan_epic(EPIC_MANIFESTS, learned)),
        ("epic-v2", lambda: launchers.scan_epic_v2(launchers.local_appdata() / launchers.EPIC_V2_DIR_NAME, learned)),
        ("gog", lambda: scan_gog(learned)),
        ("meta", lambda: launchers.scan_meta(launchers.meta_libraries(), learned)),
    ]
    seen_dirs: set[str] = set()
    for name, fn in scanners:
        try:
            for game in fn():
                folder = game.install_dir.lower().rstrip("\\")
                if folder in seen_dirs:
                    continue  # e.g. Epic launcher v1 and v2 both know the game
                seen_dirs.add(folder)
                games.append(game)
        except Exception:
            log.exception("library scan failed: %s", name)
    apps: list[InstalledGame] = []
    try:
        from gpucc.library.apps import scan_start_menu
        from gpucc.platform.win32.shell_link import com_apartment, resolve_shortcut

        with com_apartment():
            # Programs inside a game folder (game launchers' own shortcuts) are shown as the game.
            apps = scan_start_menu(resolve_shortcut, skip_dirs=[g.install_dir for g in games])
    except Exception:
        log.exception("library scan failed: start menu")
    log.info("library scan", extra={"fields": {"games": len(games), "apps": len(apps)}})
    return sorted([*games, *apps], key=lambda g: g.name.lower())


def game_for_exe(games: Sequence[InstalledGame], exe_path: str) -> InstalledGame | None:
    """The installed game whose folder contains ``exe_path`` (deepest folder wins).

    Programs (Start Menu) only match their exact exe – their folders can be broad.
    """
    p = exe_path.lower()
    exact = [g for g in games if not g.is_game and (g.exe_path or "").lower() == p]
    if exact:
        return exact[0]
    hits = [g for g in games if g.is_game and p.startswith(g.install_dir.lower().rstrip("\\") + "\\")]
    return max(hits, key=lambda g: len(g.install_dir)) if hits else None


def learn_render_exes(games: Sequence[InstalledGame], gpu_exes: Iterable[str]) -> dict[str, str]:
    """New 'learned' render executables: game key → exe that was seen using the GPU (pure)."""
    learned: dict[str, str] = {}
    for exe in gpu_exes:
        game = game_for_exe(games, exe)
        if game is None or not game.is_game:
            continue
        if game.exe_source is ExeSource.LEARNED and (game.exe_path or "").lower() == exe.lower():
            continue
        learned[game.key] = exe
    return learned
