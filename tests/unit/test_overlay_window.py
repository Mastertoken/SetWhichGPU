from PySide6.QtCore import QEvent, Qt

from gpucc.core.models import Confidence, ObservedGpu, ProcessGpuSummary, TargetApp
from gpucc.ui.overlay.viewmodel import build_state
from gpucc.ui.overlay.window import OverlayWindow


def test_render_and_escape(qtbot, discovery, keys):
    w = OverlayWindow()
    qtbot.addWidget(w)
    target = TargetApp(1, 2, r"C:\x\Unity.exe", "t", "c", file_description="Unity Editor")
    obs = ObservedGpu(keys["intel"], Confidence.HIGH, (ProcessGpuSummary(keys["intel"], 12.0, 1 << 30, {"3D": 12.0}),))
    w.apply_state(
        build_state(
            target=target, discovery=discovery, snapshot=None, observed=obs, preferred=None, hotkey_text="Strg+Alt+G"
        )
    )
    assert w.title.text() == "Unity Editor"
    assert len(w._cards) == 3
    w.apply_state(
        build_state(target=None, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="")
    )
    assert w.status_block.isHidden()

    from PySide6.QtGui import QGuiApplication

    reasons = []
    w.closed.connect(reasons.append)
    w.show_on(QGuiApplication.primaryScreen())
    qtbot.waitExposed(w)
    qtbot.keyClick(w, Qt.Key.Key_Escape)
    assert reasons == ["escape"] and not w.isVisible()


def test_process_section_toggles_on_click_and_p(qtbot, discovery, keys):
    w = OverlayWindow()
    qtbot.addWidget(w)
    target = TargetApp(1, 2, r"C:\x\blender.exe", "t", "c")
    obs = ObservedGpu(keys["nvidia"], Confidence.HIGH, (ProcessGpuSummary(keys["nvidia"], 90.0, 1 << 30, {}),))
    w.apply_state(
        build_state(target=target, discovery=discovery, snapshot=None, observed=obs, preferred=None, hotkey_text="")
    )
    w.show()
    qtbot.waitExposed(w)
    start = w.proc_label.isVisible()
    qtbot.mouseClick(w.proc_header, Qt.MouseButton.LeftButton)
    assert w.proc_label.isVisible() is not start
    assert ("▾" if w.proc_label.isVisible() else "▸") in w.proc_header.text()
    qtbot.keyClick(w, Qt.Key.Key_P)
    assert w.proc_label.isVisible() is start
    assert w._drag_offset is None  # clicking the header must not start a window drag


def test_long_status_never_squeezes_the_gpu_cards(qtbot, discovery, keys):
    """Regression: adjustSize() capped the window at 2/3 of the screen height."""
    from gpucc.assignment.win_pref import interpret
    from gpucc.i18n import set_language

    set_language("fr")  # longest texts
    w = OverlayWindow()
    qtbot.addWidget(w)
    game = TargetApp(1, 5, r"D:\Games\Game.exe", "Example Game", "c", started_at=2000.0)
    state = build_state(
        target=game,
        discovery=discovery,
        snapshot=None,
        observed=ObservedGpu(keys["nvidia"], Confidence.HIGH),
        preferred=interpret("SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;", discovery),
        hotkey_text="",
        last_change_at=1000.0,
    )
    w.apply_state(state)
    screen_h = w.screen().availableGeometry().height()
    assert w.height() >= min(w.heightForWidth(w.width()), screen_h - 16)
    assert w.height() <= screen_h


def test_subtitle_elides_before_the_buttons(qtbot, discovery):
    w = OverlayWindow()
    qtbot.addWidget(w)
    long_path = "C:\\Program Files\\" + "Very Long Folder Name\\" * 6 + "app.exe"
    target = TargetApp(1, 2, long_path, "t", "c", file_description="App")
    w.apply_state(
        build_state(target=target, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="")
    )
    assert "…" in w.subtitle.text() and w.subtitle.text().startswith("app")
    assert w.subtitle.fontMetrics().horizontalAdvance(w.subtitle.text()) <= w._subtitle_width()


def test_gpu_selection_and_apply(qtbot, discovery, keys):
    from gpucc.assignment.win_pref import interpret

    w = OverlayWindow()
    qtbot.addWidget(w)
    target = TargetApp(1, 2, r"C:\x\blender.exe", "t", "c", file_description="Blender")
    state = build_state(
        target=target,
        discovery=discovery,
        snapshot=None,
        observed=None,
        preferred=interpret("GpuPreference=2;", discovery),
        hotkey_text="",
    )
    w.apply_state(state)
    assert w.selection == keys["intel"] and not w.can_apply  # follows stored preference
    applied = []
    w.apply_requested.connect(applied.append)
    w.request_apply()
    assert applied == []  # nothing chosen → nothing written

    w._cards[keys["nvidia"]].clicked.emit()
    assert w.selection == keys["nvidia"] and w.can_apply
    w.apply_state(state)  # live refresh must not reset the user's pick
    assert w.selection == keys["nvidia"]
    qtbot.keyClick(w, Qt.Key.Key_Return)
    assert applied == [keys["nvidia"]]

    w.mark_applied()
    w.apply_state(state)  # after apply the selection follows the (re-read) preference again
    assert w.selection == keys["intel"]
    w.default_card.clicked.emit()
    assert w.selection is None and w.can_apply
    qtbot.keyClick(w, Qt.Key.Key_Down)  # None → first GPU
    assert w.selection == discovery.gpus[0].key


def test_selection_disabled_for_protected_process(qtbot, discovery, keys):
    w = OverlayWindow()
    qtbot.addWidget(w)
    t = TargetApp(1, 4, None, "Secure", "Cls", access_denied=True)
    w.apply_state(
        build_state(target=t, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="")
    )
    w.select(keys["nvidia"])
    assert w.selection is None and not w.can_apply
    assert "geschützt" in w.apply_hint.text()


def test_apps_panel(qtbot):
    from PySide6.QtGui import QGuiApplication

    from gpucc.ui.overlay.applist import AppGroup, AppListRow

    w = OverlayWindow()
    qtbot.addWidget(w)
    w.show_on(QGuiApplication.primaryScreen())
    qtbot.waitExposed(w)
    toggled, picked, follow = [], [], []
    w.apps_panel_toggled.connect(toggled.append)
    w.app_selected.connect(picked.append)
    w.follow_requested.connect(lambda: follow.append(True))
    width = w.width()
    qtbot.keyClick(w, Qt.Key.Key_L)
    assert w.apps_open and toggled == [True] and w.width() > width

    rows = [
        AppListRow("c:\\a\\aom.exe", "Age of Mythology", "nutzt RTX", AppGroup.RUNNING, 99.0),
        AppListRow("c:\\b\\blender.exe", "Blender", "bevorzugt RTX", AppGroup.SAVED, 0.0),
    ]
    w.set_app_list(rows, current_key="c:\\a\\aom.exe", following=True)
    panel = w.apps_panel
    assert panel.list.count() == 4  # 2 group headers + 2 apps
    assert panel.follow_button.isHidden()
    panel._on_item(panel.list.item(3))
    assert picked == ["c:\\b\\blender.exe"]

    panel.search.setText("blend")
    assert panel.list.item(1).isHidden() and not panel.list.item(3).isHidden()
    assert panel.list.item(0).isHidden()  # empty group header hidden too

    w.set_app_list(rows, current_key="c:\\b\\blender.exe", following=False)
    assert not panel.follow_button.isHidden()
    panel.follow_button.click()
    assert follow == [True]
    w.set_apps_open(False)
    assert not w.apps_open and w.width() == width


def _rows(n, load=0.0, order=None):
    from gpucc.ui.overlay.applist import AppGroup, AppListRow

    idx = order or range(n)
    return [AppListRow(f"k{i}", f"App {i}", f"nutzt Arc {load:.0f} %", AppGroup.RUNNING, load) for i in idx]


def test_rescan_button_and_f5(qtbot):
    from PySide6.QtGui import QGuiApplication

    w = OverlayWindow()
    qtbot.addWidget(w)
    w.show_on(QGuiApplication.primaryScreen())
    qtbot.waitExposed(w)
    requests = []
    w.rescan_requested.connect(lambda: requests.append(True))
    qtbot.keyClick(w, Qt.Key.Key_F5)  # opens the panel and requests a rescan
    assert w.apps_open and requests == [True]
    panel = w.apps_panel
    panel.set_scan_state(True, None)
    assert not panel.rescan_button.isEnabled() and "eingelesen" in panel.scan_status.text()
    qtbot.keyClick(w, Qt.Key.Key_F5)  # ignored while a scan is running
    assert requests == [True]
    panel.set_scan_state(False, (37, 24))
    assert panel.rescan_button.isEnabled() and panel.scan_status.text() == "24 Programme · 37 Spiele gefunden"
    panel.rescan_button.click()
    assert requests == [True, True]


def test_app_list_updates_in_place_without_scroll_jump(qtbot):
    from gpucc.ui.overlay.window import _AppPanel

    panel = _AppPanel()
    qtbot.addWidget(panel)
    panel.resize(270, 200)
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_rows(_rows(30), "k3", True)
    bar = panel.list.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    pos = bar.value()
    item_before = panel.list.item(10)

    panel.set_rows(_rows(30, load=42.0), "k3", True)  # only texts change (every 3 s refresh)
    assert panel.list.item(10) is item_before  # no rebuild
    assert bar.value() == pos
    assert "42 %" in panel._labels["k9"][1].text()


def test_app_list_reorder_waits_while_user_scrolls(qtbot, monkeypatch):
    from gpucc.ui.overlay.window import _AppPanel

    panel = _AppPanel()
    qtbot.addWidget(panel)
    panel.set_rows(_rows(5), None, True)
    monkeypatch.setattr(panel, "_user_is_scrolling", lambda: True)
    panel.set_rows(_rows(6), None, True)  # new app appeared
    assert panel.list.count() == 6  # 1 header + 5 apps, unchanged for now
    assert panel._pending is not None
    monkeypatch.setattr(panel, "_user_is_scrolling", lambda: False)
    panel.eventFilter(panel.list, QEvent(QEvent.Type.Leave))  # mouse leaves the list
    assert panel.list.count() == 7 and panel._pending is None


def test_smooth_wheel_animates_to_target(qtbot):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    from gpucc.ui.overlay.window import WHEEL_STEP_PX, _AppPanel

    panel = _AppPanel()
    qtbot.addWidget(panel)
    panel.resize(270, 200)
    panel.show()
    qtbot.waitExposed(panel)
    panel.set_rows(_rows(40), None, True)
    bar = panel.list.verticalScrollBar()
    bar.setValue(0)

    def notch(dy):
        return QWheelEvent(
            QPointF(10, 10),
            QPointF(10, 10),
            QPoint(0, 0),
            QPoint(0, dy),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )

    assert panel._wheel.eventFilter(panel.list.viewport(), notch(-120))  # consumed → animated
    assert panel._wheel.eventFilter(panel.list.viewport(), notch(-120))  # second notch accumulates
    qtbot.waitUntil(lambda: bar.value() == min(2 * WHEEL_STEP_PX, bar.maximum()), timeout=1000)
    assert panel._wheel.recently_used()


def test_pinning(qtbot):
    from PySide6.QtGui import QGuiApplication

    w = OverlayWindow()
    qtbot.addWidget(w)
    changes = []
    w.pinned_changed.connect(changes.append)
    w.show_on(QGuiApplication.primaryScreen())
    qtbot.waitExposed(w)
    qtbot.keyClick(w, Qt.Key.Key_A)
    assert w.pinned and "Angeheftet" in w.pin_button.text() and "A lösen" in w.footer.text()
    w.pin_button.click()
    assert not w.pinned
    w.set_pinned(True)
    w.dismiss("hotkey")  # closing always unpins → next open is transient again
    assert not w.pinned and not w.isVisible()
    assert changes == [True, False, True, False]


def test_remembers_dragged_position(qtbot):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QGuiApplication

    screen = QGuiApplication.primaryScreen()
    w = OverlayWindow()
    qtbot.addWidget(w)
    w.show_on(screen)
    qtbot.waitExposed(w)
    target = screen.availableGeometry().topLeft() + QPoint(50, 60)
    w._positions[screen.name()] = target  # what mouseReleaseEvent stores after a drag
    w.dismiss("escape")
    w.show_on(screen)
    assert w.pos() == target
