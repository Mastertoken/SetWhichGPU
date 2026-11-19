"""Programs the user adds by hand ("+ Add program")."""

from gpucc.core.models import TargetApp
from gpucc.ui.overlay.applist import AppGroup, build_app_list, valid_program_path


def test_only_existing_exe_files_are_accepted(tmp_path):
    exe = tmp_path / "Tool.EXE"
    exe.write_bytes(b"MZ")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "folder.exe").mkdir()
    assert valid_program_path(str(exe)) == str(exe)
    assert valid_program_path(str(tmp_path / "sub" / ".." / "Tool.EXE")) == str(exe)  # normalised
    for bad in (
        "",
        str(tmp_path / "missing.exe"),
        str(tmp_path / "notes.txt"),
        str(tmp_path / "folder.exe"),
        str(exe) + "\x00.txt",
        "\\\\?\\" + str(exe),
        "x" * 2000 + ".exe",
    ):
        assert valid_program_path(bad) is None, bad


def _list(discovery, custom, running=()):
    return build_app_list(
        running=list(running),
        background=[],
        saved_values={},
        profile_paths=[],
        describe_exe=lambda p: TargetApp(0, 0, p, "", "", file_description=p.rsplit("\\", 1)[-1][:-4]),
        discovery=discovery,
        history=[],
        parents={},
        custom_paths=custom,
    )


def test_added_programs_get_their_own_group_and_can_be_removed(discovery):
    rows, targets = _list(discovery, [r"D:\Tools\MyRenderer.exe"])
    (row,) = [r for r in rows if r.key == r"d:\tools\myrenderer.exe"]
    assert row.group is AppGroup.CUSTOM and row.custom and row.title == "MyRenderer"
    assert targets[row.key].exe_path == r"D:\Tools\MyRenderer.exe"


def test_running_added_program_stays_in_running_but_is_still_removable(discovery):
    running = [TargetApp(1, 5, r"D:\Tools\MyRenderer.exe", "w", "c", file_description="MyRenderer")]
    rows, _ = _list(discovery, [r"D:\Tools\MyRenderer.exe"], running)
    (row,) = [r for r in rows if r.key == r"d:\tools\myrenderer.exe"]
    assert row.group is AppGroup.RUNNING and row.custom


def test_file_dialog_does_not_close_the_overlay(qtbot, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from gpucc.ui.overlay.window import OverlayWindow

    w = OverlayWindow()
    qtbot.addWidget(w)
    seen = {}

    def fake_dialog(parent, *args):
        seen["dialog_open"] = parent._dialog_open
        return r"C:\x\App.exe", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake_dialog))
    chosen = []
    w.program_chosen.connect(chosen.append)
    w.apps_panel.add_button.click()
    assert seen == {"dialog_open": True} and chosen == [r"C:\x\App.exe"] and not w._dialog_open
