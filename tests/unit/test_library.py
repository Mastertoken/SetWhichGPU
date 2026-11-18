import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from gpucc.core.models import TargetApp
from gpucc.library.exe_resolver import resolve_render_exe
from gpucc.library.models import ExeSource, InstalledGame
from gpucc.library.scanner import game_for_exe, learn_render_exes, scan_epic, scan_steam
from gpucc.library.steam import APPINFO_MAGIC_V29, launch_executable, parse_appinfo
from gpucc.ui.overlay.applist import AppGroup, build_app_list


# --------------------------------------------------------------------------- binary appinfo builder
def build_appinfo(apps: dict[int, dict]) -> bytes:
    """Minimal appinfo.vdf v29 writer for tests (string-table keys)."""
    keys: list[str] = []

    def kid(k: str) -> bytes:
        if k not in keys:
            keys.append(k)
        return struct.pack("<I", keys.index(k))

    def kv(node: dict) -> bytes:
        out = b""
        for k, v in node.items():
            if isinstance(v, dict):
                out += b"\x00" + kid(k) + kv(v)
            elif isinstance(v, int):
                out += b"\x02" + kid(k) + struct.pack("<i", v)
            else:
                out += b"\x01" + kid(k) + str(v).encode() + b"\x00"
        return out + b"\x08"

    body = b""
    for appid, tree in apps.items():
        data = b"\x00" + kid("appinfo") + kv(tree) + b"\x08"
        header = struct.pack("<IIQ20sI20s", 0, 0, 0, b"\0" * 20, 0, b"\0" * 20)
        body += struct.pack("<II", appid, len(header) + len(data)) + header + data
    body += struct.pack("<I", 0)
    table = struct.pack("<I", len(keys)) + b"".join(k.encode() + b"\x00" for k in keys)
    return struct.pack("<IIq", APPINFO_MAGIC_V29, 1, 16 + len(body)) + body + table


def launch(*opts: dict) -> dict:
    return {"config": {"launch": {str(i): o for i, o in enumerate(opts)}}}


def test_appinfo_roundtrip_and_launch_selection():
    data = build_appinfo(
        {
            1934680: launch({"executable": "AoMRT_s.exe", "type": "default"}),
            289070: launch(
                {"executable": "Base/Binaries/Win64Steam/CivilizationVI_DX12.exe", "type": "option1"},
                {"executable": "LaunchPad/LaunchPad.exe", "type": "default"},
            ),
            1: launch({"executable": "game.sh", "config": {"oslist": "linux"}}),
        }
    )
    apps = parse_appinfo(data)
    assert launch_executable(apps["1934680"]) == "AoMRT_s.exe"
    assert launch_executable(apps["289070"]) == r"LaunchPad\LaunchPad.exe"  # default wins
    assert launch_executable(apps["1"]) is None  # no Windows exe


def test_appinfo_rejects_unknown_version():
    with pytest.raises(ValueError):
        parse_appinfo(struct.pack("<IIq", 0x07564428, 1, 16) + b"\0" * 8)


# --------------------------------------------------------------------------- exe resolution
def touch(p: Path, size: int = 10) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * size)
    return p


def test_unreal_stub_resolves_to_shipping_exe(tmp_path):
    stub = touch(tmp_path / "TheInvincible.exe")
    ship = touch(tmp_path / "TheInvincible" / "Binaries" / "Win64" / "TheInvincible-Win64-Shipping.exe")
    assert resolve_render_exe(tmp_path, stub) == (str(ship), ExeSource.GUESSED)


def test_launcher_falls_back_to_largest_game_exe(tmp_path):
    starter = touch(tmp_path / "start_protected_game.exe", 500)
    game = touch(tmp_path / "bin" / "helldivers2.exe", 5000)
    touch(tmp_path / "tools" / "CrashReporter.exe", 9000)  # never chosen
    touch(tmp_path / "_CommonRedist" / "vc_redist.x64.exe", 9000)
    assert resolve_render_exe(tmp_path, starter) == (str(game), ExeSource.GUESSED)


def test_plain_launch_exe_and_learned_override(tmp_path):
    exe = touch(tmp_path / "AoMRT_s.exe")
    other = touch(tmp_path / "bin" / "real.exe")
    assert resolve_render_exe(tmp_path, exe) == (str(exe), ExeSource.LAUNCHER)
    assert resolve_render_exe(tmp_path, exe, learned=str(other)) == (str(other), ExeSource.LEARNED)
    assert resolve_render_exe(tmp_path, exe, learned=str(tmp_path / "gone.exe"))[1] is ExeSource.LAUNCHER


# --------------------------------------------------------------------------- scanners
def test_scan_steam_dedupes_and_skips_missing(tmp_path):
    root = tmp_path / "Steam"
    lib2 = tmp_path / "Lib2"
    (root / "steamapps").mkdir(parents=True)
    (root / "appcache").mkdir()
    (root / "steamapps" / "libraryfolders.vdf").write_text(
        f'"libraryfolders" {{ "0" {{ "path" "{str(root).replace(chr(92), chr(92) * 2)}" }}'
        f' "1" {{ "path" "{str(lib2).replace(chr(92), chr(92) * 2)}" }} }}'
    )

    def manifest(lib: Path, appid: str, name: str, folder: str) -> None:
        (lib / "steamapps").mkdir(parents=True, exist_ok=True)
        (lib / "steamapps" / f"appmanifest_{appid}.acf").write_text(
            f'"AppState" {{ "appid" "{appid}" "name" "{name}" "installdir" "{folder}" }}'
        )

    manifest(root, "1934680", "Age of Mythology: Retold", "AoM")
    manifest(lib2, "1934680", "Age of Mythology: Retold", "AoM")  # stale duplicate
    manifest(root, "228980", "Steamworks Common Redistributables", "Redist")
    manifest(root, "684380", "Mermaid VR", "Mermaid")  # folder missing
    touch(root / "steamapps" / "common" / "AoM" / "AoMRT_s.exe")
    (root / "steamapps" / "common" / "Redist").mkdir()
    (root / "appcache" / "appinfo.vdf").write_bytes(build_appinfo({1934680: launch({"executable": "AoMRT_s.exe"})}))
    games = scan_steam(root, {})
    assert [(g.name, Path(g.exe_path).name, g.exe_source) for g in games] == [
        ("Age of Mythology: Retold", "AoMRT_s.exe", ExeSource.LAUNCHER)
    ]


def test_scan_epic(tmp_path):
    game_dir = tmp_path / "Fortnite"
    exe = touch(game_dir / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe")
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    (manifests / "a.item").write_text(
        json.dumps(
            {
                "DisplayName": "Fortnite",
                "AppName": "Fortnite",
                "InstallLocation": str(game_dir),
                "LaunchExecutable": "FortniteGame/Binaries/Win64/FortniteClient-Win64-Shipping.exe",
            }
        )
    )
    (manifests / "b.item").write_text(json.dumps({"bIsIncompleteInstall": True, "InstallLocation": str(game_dir)}))
    [g] = scan_epic(manifests, {})
    assert g.store == "Epic" and Path(g.exe_path) == exe


# --------------------------------------------------------------------------- learning + list
GAME = InstalledGame(
    "Steam",
    "731040",
    "The Invincible",
    r"H:\Lib\common\The Invincible",
    r"H:\Lib\common\The Invincible\TheInvincible.exe",
    ExeSource.GUESSED,
)


def test_learning_render_exe():
    shipping = r"H:\Lib\common\The Invincible\TheInvincible\Binaries\Win64\TheInvincible-Win64-Shipping.exe"
    assert game_for_exe([GAME], shipping) is GAME
    assert learn_render_exes([GAME], [shipping, r"C:\Windows\explorer.exe"]) == {"steam:731040": shipping}
    already = replace(GAME, exe_path=shipping, exe_source=ExeSource.LEARNED)
    assert learn_render_exes([already], [shipping.upper()]) == {}  # nothing new to store


def test_installed_games_in_app_list(discovery):
    aom = InstalledGame(
        "Steam", "1934680", "Age of Mythology: Retold", r"H:\Lib\AoM", r"H:\Lib\AoM\AoMRT_s.exe", ExeSource.LAUNCHER
    )
    elite = InstalledGame("Steam", "359320", "Elite Dangerous", r"H:\Lib\Elite", None, ExeSource.GUESSED)

    def describe(path):
        return TargetApp(hwnd=0, pid=0, exe_path=path, title="", window_class="", file_description="AoMRT_s")

    rows, targets = build_app_list(
        running=[],
        background=[],
        saved_values={r"H:\Lib\AoM\AoMRT_s.exe": "SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;"},
        profile_paths=[],
        describe_exe=describe,
        discovery=discovery,
        history=[],
        parents={},
        games=[aom, GAME, elite],
    )
    assert [(r.group, r.title) for r in rows] == [
        (AppGroup.SAVED, "Age of Mythology: Retold"),  # store name instead of "AoMRT_s"
        (AppGroup.INSTALLED, "Elite Dangerous"),
        (AppGroup.INSTALLED, "The Invincible"),
    ]
    by_title = {r.title: r for r in rows}
    assert by_title["Elite Dangerous"].subtitle == "Steam · EXE noch unbekannt"
    assert by_title["Age of Mythology: Retold"].subtitle == "bevorzugt Arc Pro B65"
    inv = targets[GAME.exe_path.lower()]
    assert inv.display_name == "The Invincible" and "geschätzt" in (inv.exe_note or "")
    assert targets["steam:359320"].exe_path is None
