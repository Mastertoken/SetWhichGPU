"""Side-panel application list (pure → unit-testable).

Groups: running apps (window), background GPU processes (no window), saved preferences of apps
that are not running, installed games. One row per application (case-insensitive exe path).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from gpucc.assignment.win_pref import interpret
from gpucc.core.models import Confidence, DiscoveryResult, GpuKey, GpuSnapshot, TargetApp
from gpucc.i18n import tr
from gpucc.library.models import ExeSource, InstalledGame
from gpucc.library.scanner import game_for_exe
from gpucc.monitoring.attribution import observe, process_tree

#: Windowless processes are listed only above these thresholds.
BACKGROUND_MIN_RENDER_PCT = 1.0
BACKGROUND_MIN_VRAM = 256 << 20
#: Apps above this render load are sorted into the "active" block at the top of their group.
ACTIVE_THRESHOLD_PCT = 1.0


def exe_note(source: ExeSource) -> str | None:
    return {
        ExeSource.LAUNCHER: None,
        ExeSource.LEARNED: tr("Game executable detected during the last session."),
        ExeSource.GUESSED: tr("Game executable estimated (launcher ≠ game process) – confirmed on first play."),
    }[source]


class AppGroup(StrEnum):
    RUNNING = "running"
    BACKGROUND = "background"
    SAVED = "saved"
    INSTALLED_APPS = "installed_apps"
    INSTALLED = "installed_games"

    @property
    def label(self) -> str:
        return {
            AppGroup.RUNNING: tr("Running"),
            AppGroup.BACKGROUND: tr("Background (no window)"),
            AppGroup.SAVED: tr("Saved – not running"),
            AppGroup.INSTALLED_APPS: tr("Installed programs"),
            AppGroup.INSTALLED: tr("Installed games"),
        }[self]


@dataclass(frozen=True, slots=True)
class AppListRow:
    key: str
    title: str
    subtitle: str
    group: AppGroup
    activity: float  # render % – sorts active apps to the top


def background_candidates(snapshot: GpuSnapshot | None) -> list[int]:
    """PIDs with noticeable GPU use (render activity or VRAM) in the latest snapshot."""
    if snapshot is None:
        return []
    render: dict[int, float] = {}
    vram: dict[int, int] = {}
    for p in snapshot.processes:
        render[p.pid] = render.get(p.pid, 0.0) + sum(
            v for e, v in p.engines.items() if e.startswith(("3D", "Compute", "Cuda"))
        )
        vram[p.pid] = vram.get(p.pid, 0) + p.dedicated_bytes
    pids = set(render) | set(vram)
    return sorted(
        pid
        for pid in pids
        if render.get(pid, 0.0) >= BACKGROUND_MIN_RENDER_PCT or vram.get(pid, 0) >= BACKGROUND_MIN_VRAM
    )


def _short(discovery: DiscoveryResult, key: GpuKey | None) -> str | None:
    g = discovery.by_key(key) if key else None
    return g.short_name if g else None


def with_game(target: TargetApp, games: Sequence[InstalledGame]) -> TargetApp:
    """Label an app with its store name if its exe belongs to an installed game."""
    game = game_for_exe(games, target.exe_path) if target.exe_path else None
    if game is None or target.label:
        return target
    return replace(target, label=game.name)


def game_target(game: InstalledGame, describe_exe: Callable[[str], TargetApp]) -> TargetApp:
    if game.exe_path:
        base = describe_exe(game.exe_path)
    else:
        base = TargetApp(hwnd=0, pid=0, exe_path=None, title="", window_class="")
    note = game.note or (exe_note(game.exe_source) if game.is_game and game.exe_path else None)
    return replace(base, label=game.name, exe_note=note)


def build_app_list(
    *,
    running: Sequence[TargetApp],
    background: Sequence[TargetApp],
    saved_values: Mapping[str, str],
    profile_paths: Sequence[str],
    describe_exe: Callable[[str], TargetApp],
    discovery: DiscoveryResult,
    history: Sequence[GpuSnapshot],
    parents: Mapping[int, int],
    games: Sequence[InstalledGame] = (),
) -> tuple[list[AppListRow], dict[str, TargetApp]]:
    saved_by_key = {path.lower(): (path, value) for path, value in saved_values.items()}
    targets: dict[str, TargetApp] = {}
    rows: list[AppListRow] = []
    game_by_exe = {g.exe_path.lower(): g for g in games if g.exe_path}
    listed_games: set[str] = set()

    def add(target: TargetApp, group: AppGroup, key: str | None = None, store: str | None = None) -> None:
        key = key or target.app_key
        if key in targets:
            return
        targets[key] = target
        raw = saved_by_key.get(target.app_key, (None, None))[1]
        pref = interpret(raw, discovery)
        pref_name = _short(discovery, pref.choice)
        parts: list[str] = [store] if store else []
        activity = 0.0
        if target.running:
            obs = observe(process_tree(target.pid, dict(parents)), history)
            if obs.confidence is not Confidence.NONE and obs.key is not None:
                activity = obs.per_gpu[0].render_pct if obs.per_gpu else 0.0
                load = f" {activity:.0f} %" if obs.confidence is Confidence.HIGH else ""
                parts.append(tr("uses {gpu}", gpu=f"{_short(discovery, obs.key)}{load}"))
            else:
                parts.append(tr("no GPU load"))
        elif target.exe_missing:
            parts.append(tr("program file missing"))
        elif not target.exe_path:
            parts.append(tr("executable not known yet"))
        if pref.stale:
            parts.append(tr("preferred: GPU missing"))
        elif pref_name:
            parts.append(tr("preferred {gpu}", gpu=pref_name))
        rows.append(AppListRow(key, target.display_name, " · ".join(parts), group, activity))

    for t in running:
        add(with_game(t, games), AppGroup.RUNNING)
    for t in background:
        add(with_game(t, games), AppGroup.BACKGROUND)
    for path in [*(p for p, _ in saved_by_key.values()), *profile_paths]:
        if path.lower() in targets:
            continue
        game = game_by_exe.get(path.lower())
        if game is not None:
            listed_games.add(game.key)
            add(game_target(game, describe_exe), AppGroup.SAVED)
        else:
            add(with_game(describe_exe(path), games), AppGroup.SAVED)
    for game in games:
        exe_key = (game.exe_path or "").lower()
        if game.key in listed_games or (exe_key and exe_key in targets):
            continue
        if game.is_game:
            add(game_target(game, describe_exe), AppGroup.INSTALLED, key=exe_key or game.key, store=game.store)
        else:
            add(game_target(game, describe_exe), AppGroup.INSTALLED_APPS, key=exe_key or game.key)

    # Stable order (no reshuffling on 98 % vs 99 %): active apps first, then alphabetical.
    order = list(AppGroup)
    rows.sort(key=lambda r: (order.index(r.group), r.activity < ACTIVE_THRESHOLD_PCT, r.title.lower()))
    return rows, targets
