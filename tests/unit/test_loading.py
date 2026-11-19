"""Loading animation of the application list and version-info prewarming off the UI thread."""

import threading

from gpucc.library import service as library_service
from gpucc.library.models import ExeSource, InstalledGame
from gpucc.library.service import LibraryService
from gpucc.ui.overlay.applist import AppGroup, AppListRow
from gpucc.ui.overlay.window import OverlayWindow


def test_spinner_replaces_the_list_while_loading_and_animates_only_when_visible(qtbot):
    w = OverlayWindow()
    qtbot.addWidget(w)
    w.show()
    w.set_apps_open(True)
    panel = w.apps_panel
    assert not panel.has_rows
    panel.set_loading(True)
    assert panel.spinner.isVisible() and not panel.list.isVisible()
    assert panel.spinner._timer.isActive()
    angle = panel.spinner._angle
    qtbot.waitUntil(lambda: panel.spinner._angle != angle, timeout=1000)  # it really rotates
    panel.set_rows([AppListRow("k", "App", "", AppGroup.RUNNING, 0.0)], None, True)
    assert panel.has_rows
    panel.set_loading(False)
    assert not panel.spinner.isVisible() and panel.list.isVisible()
    assert not panel.spinner._timer.isActive()  # no CPU spent on a hidden animation


def test_scan_prewarms_version_info_on_the_worker_thread(qtbot, monkeypatch):
    game = InstalledGame("Steam", "1", "Game", r"D:\G", r"D:\G\game.exe", ExeSource.LAUNCHER)
    monkeypatch.setattr(library_service, "scan_all", lambda learned: [game])
    seen: dict[str, object] = {}

    def prewarm(paths):
        seen["paths"] = list(paths)
        seen["thread"] = threading.current_thread().name

    svc = LibraryService(lambda: {}, prewarm=prewarm, extra_paths=lambda: [r"C:\saved\tool.exe"])
    with qtbot.waitSignal(svc.games_ready, timeout=3000):
        svc.rescan()
    assert seen == {"paths": [r"D:\G\game.exe", r"C:\saved\tool.exe"], "thread": "gpucc-library"}
