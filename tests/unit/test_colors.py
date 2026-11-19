"""Each graphics card has its own colour – on its card and in the application list."""

from dataclasses import replace

from gpucc.core.models import DiscoveryResult, GpuSnapshot, ProcessGpuUsage, TargetApp
from gpucc.ui.overlay.applist import AppGroup, AppListRow, build_app_list
from gpucc.ui.overlay.colors import EXTRA_COLORS, VENDOR_COLORS, dimmed, gpu_colors
from gpucc.ui.overlay.viewmodel import build_state


def test_vendor_colours_and_distinct_for_same_vendor(discovery):
    colors = gpu_colors(discovery)
    by_vendor = {g.vendor.value: colors[g.key] for g in discovery.gpus}
    assert by_vendor == VENDOR_COLORS
    nvidia = next(g for g in discovery.gpus if g.vendor.value == "nvidia")
    twin = replace(
        nvidia, key=replace(nvidia.key, revision=nvidia.key.revision + 1)
    )  # a second card of the same vendor
    two = DiscoveryResult(gpus=(nvidia, twin), ignored=(), display_gpus=frozenset())
    c = gpu_colors(two)
    assert c[nvidia.key] == VENDOR_COLORS["nvidia"] and c[twin.key] == EXTRA_COLORS[0]


def test_card_rows_carry_their_colour(discovery):
    s = build_state(target=None, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="")
    assert {r.color for r in s.gpus} == set(VENDOR_COLORS.values())


def test_app_list_rows_take_the_colour_of_the_gpu_they_use(discovery, keys):
    arc = keys["intel"]
    running = [
        TargetApp(1, 10, r"C:\a\Busy.exe", "Busy", "c"),
        TargetApp(2, 20, r"C:\a\Idle.exe", "Idle", "c"),
    ]
    snap = GpuSnapshot(
        0.0,
        (),
        (
            ProcessGpuUsage(10, arc, {"3D": 40.0}, 1 << 30),
            ProcessGpuUsage(30, arc, {"3D": 0.0}, 1 << 30),  # only holds memory, no load
        ),
    )
    running.append(TargetApp(3, 30, r"C:\a\Resident.exe", "Resident", "c"))
    rows, _ = build_app_list(
        running=running,
        background=[],
        saved_values={},
        profile_paths=[],
        describe_exe=lambda p: TargetApp(0, 0, p, "", ""),
        discovery=discovery,
        history=[snap],
        parents={},
    )
    color = {r.title: r.color for r in rows}
    assert color["Busy"] == VENDOR_COLORS["intel"] and color["Idle"] == ""
    assert color["Resident"] == dimmed(VENDOR_COLORS["intel"]) != VENDOR_COLORS["intel"]


def test_dimmed_is_darker_and_safe():
    assert dimmed("#5CB3FF") == "#3F6C94"  # halfway towards the panel background
    assert dimmed("not a colour") == "not a colour" and dimmed("#ZZZZZZ") == "#ZZZZZZ"


def test_app_list_colour_cannot_inject_styles(qtbot):
    from gpucc.ui.overlay.window import _AppPanel

    evil = AppListRow("k", "<b>x</b>", "", AppGroup.RUNNING, 0.0, color="red;background:url(http://x)")
    html = _AppPanel._html(evil)
    assert "url(" not in html and "&lt;b&gt;" in html
    ok = _AppPanel._html(replace(evil, color="#5CB3FF"))
    assert "color:#5CB3FF" in ok
