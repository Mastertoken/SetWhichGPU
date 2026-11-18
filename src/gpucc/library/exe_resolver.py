"""Which executable of a game actually renders? (launchers/stubs ≠ render process)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from gpucc.library.models import ExeSource

#: Executables that never render the game.
SKIP_EXE = re.compile(
    r"(?i)(crash|report|unins|setup|install|redist|dxsetup|directx|dotnet|prereq|easyanticheat|eac_|"
    r"battleye|be_service|helper|updater|cefprocess|webhelper|benchmark|bugsplat|dumper|vconsole|"
    r"zfgamebrowser|bssndrpt|aoeurl|testwebclient|7z|python|java|node)"
)
SKIP_DIRS = frozenset({"_commonredist", "redist", "support", "plugins", "__installer", "directx", "dotnet"})
#: Launch executables that only start the real game process.
LAUNCHER_EXE = re.compile(r"(?i)(launch|start_protected_game|bootstrap|loader|startup)")
MAX_DEPTH = 4


def unreal_shipping_exe(install_dir: Path, launch_exe: Path) -> Path | None:
    """UE stub ``X.exe`` → ``X\\Binaries\\Win64\\X-Win64-Shipping.exe`` (or any *-Shipping.exe)."""
    stem = launch_exe.stem
    direct = install_dir / stem / "Binaries" / "Win64" / f"{stem}-Win64-Shipping.exe"
    if direct.is_file():
        return direct
    hits = sorted(install_dir.glob("*/Binaries/Win64/*-Win64-Shipping.exe"))
    return hits[0] if len(hits) == 1 else None


def largest_plausible_exe(install_dir: Path, exclude: Path | None = None) -> Path | None:
    best: tuple[int, int, Path] | None = None
    for dirpath, dirnames, files in os.walk(install_dir):
        rel = Path(dirpath).relative_to(install_dir).parts
        if len(rel) >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not SKIP_EXE.search(d)]
        for f in files:
            if not f.lower().endswith(".exe") or SKIP_EXE.search(f) or LAUNCHER_EXE.search(f):
                continue
            p = Path(dirpath) / f
            if exclude is not None and p == exclude:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            cand = (1 if f.lower().endswith("-win64-shipping.exe") else 0, size, p)
            if best is None or cand[:2] > best[:2]:
                best = cand
    return best[2] if best else None


def resolve_render_exe(
    install_dir: Path, launch_exe: Path | None, learned: str | None = None
) -> tuple[str | None, ExeSource]:
    """Best guess for the process that renders, plus how certain we are."""
    if learned and Path(learned).is_file():
        return learned, ExeSource.LEARNED
    if launch_exe is not None and launch_exe.is_file():
        shipping = unreal_shipping_exe(install_dir, launch_exe)
        if shipping is not None:
            return str(shipping), ExeSource.GUESSED
        if not LAUNCHER_EXE.search(launch_exe.name):
            return str(launch_exe), ExeSource.LAUNCHER
    guess = largest_plausible_exe(install_dir, exclude=launch_exe)
    if guess is not None:
        return str(guess), ExeSource.GUESSED
    if launch_exe is not None and launch_exe.is_file():
        return str(launch_exe), ExeSource.LAUNCHER
    return None, ExeSource.GUESSED
