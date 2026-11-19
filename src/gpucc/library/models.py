"""Library data model (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ExeSource(StrEnum):
    LAUNCHER = "launcher"  # exact: the launcher's own launch configuration (appinfo, manifest, shortcut)
    LEARNED = "learned"  # observed: the game's process was seen running from this exe
    GUESSED = "guessed"  # heuristic: starter ≠ render process, best plausible exe chosen


@dataclass(frozen=True, slots=True)
class InstalledGame:
    """An installed game (Steam/Epic/GOG) or program (Start Menu)."""

    store: str  # "Steam" | "Epic" | "GOG" | "Meta" | "StartMenu"
    game_id: str
    name: str
    install_dir: str
    exe_path: str | None
    exe_source: ExeSource
    kind: str = "game"  # "game" | "app"
    note: str | None = None  # extra hint shown in the overlay

    @property
    def key(self) -> str:
        return f"{self.store.lower()}:{self.game_id}"

    @property
    def is_game(self) -> bool:
        return self.kind == "game"
