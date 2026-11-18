from pathlib import Path

from gpucc.library.apps import resolve_app_exe, scan_start_menu
from gpucc.library.models import ExeSource, InstalledGame
from gpucc.library.scanner import game_for_exe, learn_render_exes
from gpucc.ui.overlay.applist import AppGroup, build_app_list


def touch(p: Path, size: int = 10) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\0" * size)
    return p


def test_launcher_resolves_to_sibling(tmp_path):
    launcher = touch(tmp_path / "Blender 5.3" / "blender-launcher.exe", 100)
    real = touch(tmp_path / "Blender 5.3" / "blender.exe", 5000)
    touch(tmp_path / "Blender 5.3" / "crashpad_handler.exe", 9000)  # skipped helper
    exe, source, note = resolve_app_exe(launcher)
    assert exe == real and source is ExeSource.GUESSED and "blender-launcher.exe" in (note or "")


def test_squirrel_app_resolves_to_newest_version(tmp_path):
    root = tmp_path / "Discord"
    stub = touch(root / "Discord.exe")
    touch(root / "Update.exe")
    touch(root / "app-1.0.900" / "Discord.exe")
    newest = touch(root / "app-1.0.9269" / "Discord.exe")
    touch(root / "app-1.0.99" / "Discord.exe")  # numeric, not lexical comparison
    exe, source, note = resolve_app_exe(stub)
    assert exe == newest and source is ExeSource.GUESSED and "Updates" in (note or "")


def test_plain_program(tmp_path):
    exe = touch(tmp_path / "Notepad++" / "notepad++.exe")
    assert resolve_app_exe(exe) == (exe, ExeSource.LAUNCHER, None)


def test_scan_start_menu_filters_and_dedupes(tmp_path):
    menu = tmp_path / "Start Menu"
    prog = tmp_path / "Programs"
    targets = {
        "Notepad++.lnk": touch(prog / "npp" / "notepad++.exe"),
        "Notepad++ (Kopie).lnk": prog / "npp" / "notepad++.exe",  # same exe, longer name → dropped
        "Uninstall Notepad++.lnk": touch(prog / "npp" / "uninstall.exe"),
        "Bug Reporter.lnk": touch(prog / "unity" / "UnityBugReporter.exe"),
        "Paint.lnk": Path(r"C:\Windows\System32\mspaint.exe"),
        "Website.lnk": None,  # URL shortcut → no exe target
        "Gone.lnk": prog / "gone" / "gone.exe",  # target missing
        "My Game Launcher.lnk": touch(prog / "games" / "MyGame" / "Game.exe"),  # inside a game folder
    }
    for name in targets:
        touch(menu / "Sub" / name)

    def resolve(lnk: str) -> str | None:
        t = targets[Path(lnk).name]
        return str(t) if t else None

    apps = scan_start_menu(resolve, skip_dirs=[str(prog / "games" / "MyGame")], menu_dirs=[menu])
    assert [(a.name, Path(a.exe_path).name, a.kind) for a in apps] == [("Notepad++", "notepad++.exe", "app")]


APP = InstalledGame(
    "Startmenü", r"c:\p\code.exe", "Visual Studio Code", r"C:\p", r"C:\p\Code.exe", ExeSource.LAUNCHER, kind="app"
)
GAME = InstalledGame("Steam", "1", "AoM", r"H:\L\AoM", r"H:\L\AoM\AoMRT_s.exe", ExeSource.LAUNCHER)


def test_programs_match_exact_exe_only_and_are_not_learned():
    assert game_for_exe([APP, GAME], r"C:\p\code.exe") is APP
    assert game_for_exe([APP, GAME], r"C:\p\other.exe") is None  # no folder-prefix match for programs
    assert game_for_exe([APP, GAME], r"H:\L\AoM\bin\x.exe") is GAME
    assert learn_render_exes([APP], [r"C:\p\code.exe"]) == {}


def test_programs_group_in_app_list(discovery):
    from gpucc.core.models import TargetApp

    def describe(path):
        return TargetApp(hwnd=0, pid=0, exe_path=path, title="", window_class="", file_description="Code")

    rows, targets = build_app_list(
        running=[],
        background=[],
        saved_values={},
        profile_paths=[],
        describe_exe=describe,
        discovery=discovery,
        history=[],
        parents={},
        games=[APP, GAME],
    )
    assert [(r.group, r.title, r.subtitle) for r in rows] == [
        (AppGroup.INSTALLED_APPS, "Visual Studio Code", ""),
        (AppGroup.INSTALLED, "AoM", "Steam"),
    ]
    assert targets[r"c:\p\code.exe"].display_name == "Visual Studio Code"
