"""Epic Games Launcher v2 and Meta Horizon Link libraries (files are untrusted input)."""

import json
from pathlib import Path

import pytest

from gpucc.library.launchers import contained, epic_v2_installations, scan_epic_v2, scan_meta


@pytest.mark.parametrize(
    ("relative", "ok"),
    [
        ("Game.exe", True),
        ("Engine/Binaries/Win64/UnrealEditor.exe", True),
        ("..\\..\\Windows\\System32\\cmd.exe", False),
        ("sub/../../evil.exe", False),
        ("C:\\Windows\\notepad.exe", False),
        ("\\\\server\\share\\x.exe", False),
        ("\\rooted.exe", False),
        ("", False),
    ],
)
def test_contained_rejects_paths_outside_the_game_folder(relative, ok):
    assert (contained(Path(r"D:\Games\X"), relative) is not None) is ok


def _epic_base(tmp_path: Path, entries: list[dict], catalog: dict | None = None) -> Path:
    base = tmp_path / "com.epicgames.eglv2"
    base.mkdir()
    lines = [json.dumps({"version": 1, "entries": len(entries)})] + [json.dumps(e) for e in entries]
    (base / "installations.jsonl").write_text("\n".join(lines) + "\nnot json\n", encoding="utf-8")
    if catalog is not None:
        (base / "cache" / "prod").mkdir(parents=True)
        (base / "cache" / "prod" / "catalog-cache.json").write_text(json.dumps(catalog), encoding="utf-8")
    return base


def test_epic_v2_last_entry_wins_and_titles(tmp_path):
    game = tmp_path / "SpaceShooter"
    game.mkdir()
    (game / "Shooter.exe").write_bytes(b"MZ")
    common = {"installationId": "A", "dir": str(game), "itemId": "item1", "artifactId": "art1"}
    entries = [
        {**common, "complete": False, "launchExecutable": "Shooter.exe"},
        {**common, "complete": True, "launchExecutable": "Shooter.exe"},
        {
            "installationId": "P",
            "complete": True,
            "dir": str(game),
            "parentInstallationId": "A",
            "launchExecutable": "",
        },
        {"installationId": "B", "complete": False, "dir": str(game), "launchExecutable": "x.exe"},  # still installing
        {"installationId": "E", "complete": True, "dir": str(game), "launchExecutable": "..\\..\\evil.exe"},
    ]
    base = _epic_base(tmp_path, entries, {"items": {"item1": {"item": {"title": "Space Shooter\u202e"}}}})
    assert [e["installationId"] for e in epic_v2_installations(base)] == ["A", "E"]
    (g,) = scan_epic_v2(base, {})  # E is dropped: its launch path leaves the game folder
    assert (g.store, g.game_id, g.name) == ("Epic", "art1", "Space Shooter")
    assert g.exe_path == str(game / "Shooter.exe")


def test_epic_v2_without_catalog_uses_folder_name(tmp_path):
    game = tmp_path / "SomeGame"
    game.mkdir()
    (game / "Some.exe").write_bytes(b"MZ")
    entry = {
        "installationId": "A",
        "complete": True,
        "dir": str(game),
        "artifactId": "a",
        "launchExecutable": "Some.exe",
    }
    (g,) = scan_epic_v2(_epic_base(tmp_path, [entry]), {})
    assert g.name == "SomeGame"
    assert scan_epic_v2(tmp_path / "missing", {}) == []


def test_meta_library(tmp_path):
    lib = tmp_path / "VRLibrary"
    (lib / "Manifests").mkdir(parents=True)
    beat = lib / "Software" / "beat-games-beat-saber"
    beat.mkdir(parents=True)
    (beat / "Beat Saber.exe").write_bytes(b"MZ")
    other = lib / "Software" / "ready-at-dawn-echo-arena"
    (other / "bin").mkdir(parents=True)
    (other / "bin" / "game.exe").write_bytes(b"MZ")

    def manifest(name, data):
        (lib / "Manifests" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

    manifest(
        "beat-games-beat-saber",
        {"canonicalName": "beat-games-beat-saber", "appId": "123", "launchFile": "Beat Saber.exe"},
    )
    manifest("beat-games-beat-saber_assets", {"canonicalName": "beat-games-beat-saber_assets"})
    manifest("ready-at-dawn-echo-arena", {"canonicalName": "ready-at-dawn-echo-arena", "launchFile": "bin\\game.exe"})
    manifest("oculus-runtime", {"canonicalName": "oculus-runtime", "isCore": True})
    manifest("evil", {"canonicalName": "..\\..\\Windows", "launchFile": "explorer.exe"})
    (lib / "Manifests" / "broken.json").write_text("[[[[", encoding="utf-8")

    games = {g.game_id: g for g in scan_meta([lib, tmp_path / "missing"], {})}
    assert set(games) == {"123", "ready-at-dawn-echo-arena"}
    assert games["123"].name == "Beat Saber" and games["123"].store == "Meta"
    assert games["123"].exe_path == str(beat / "Beat Saber.exe")
    assert games["ready-at-dawn-echo-arena"].name == "Ready At Dawn Echo Arena"  # generic exe name → pretty id
    assert games["123"].note == "VR-Spiel (Meta Horizon Link)"
