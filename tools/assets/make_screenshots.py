"""Render README / website screenshots of the real overlay widget with anonymised sample data.

No live system data is used: GPUs come from the test fixtures, apps and numbers are made up.

    uv run python tools/assets/make_screenshots.py [--lang en] [--out docs/assets]
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

GIB = 1 << 30


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="en")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "assets")
    args = parser.parse_args()

    from conftest import ADAPTERS, DEVICES, LUID_ARC, ORDER_DEFAULT, ORDER_HIGH, ORDER_MIN
    from PySide6.QtWidgets import QApplication

    from gpucc.assignment.win_pref import interpret
    from gpucc.core.models import (
        Confidence,
        GpuSnapshot,
        GpuTelemetry,
        ObservedGpu,
        ProcessGpuSummary,
        TargetApp,
    )
    from gpucc.discovery.merge import merge
    from gpucc.i18n import set_language
    from gpucc.ui.overlay.applist import AppGroup, AppListRow
    from gpucc.ui.overlay.viewmodel import build_state, gamemode_offer
    from gpucc.ui.overlay.window import OverlayWindow

    set_language(args.lang)
    app = QApplication(sys.argv)
    disc = merge(ADAPTERS, DEVICES, ORDER_HIGH, ORDER_MIN, ORDER_DEFAULT, output_counts={LUID_ARC: 2})
    keys = {g.vendor.value: g.key for g in disc.gpus}
    arc, nv, amd = keys["intel"], keys["nvidia"], keys["amd"]
    args.out.mkdir(parents=True, exist_ok=True)

    def snapshot(util: dict, vram: dict) -> GpuSnapshot:
        temps = {arc: 54.0, nv: 71.0, amd: None}
        power = {arc: 61.0, nv: 158.0, amd: None}
        return GpuSnapshot(
            0,
            tuple(
                GpuTelemetry(
                    g.key, util[g.key], {}, vram[g.key], g.dedicated_vram_bytes, temps[g.key], power[g.key], ("pdh",)
                )
                for g in disc.gpus
            ),
            (),
        )

    from gpucc.core.hotkey import DEFAULT_HOTKEY, parse_hotkey

    hotkey = str(parse_hotkey(DEFAULT_HOTKEY))  # localized

    # 1) Blender rendering on the RTX, preference set to the RTX, application list open.
    blender = TargetApp(
        1,
        4242,
        r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe",
        "Blender",
        "GHOST_WindowClass",
        product_name="Blender",
        file_description="Blender",
    )
    observed = ObservedGpu(
        nv,
        Confidence.HIGH,
        (
            ProcessGpuSummary(nv, 97.0, int(7.4 * GIB), {"Compute (CUDA)": 97.0}),
            ProcessGpuSummary(arc, 6.0, int(0.6 * GIB), {"3D": 6.0}),
        ),
    )
    state = build_state(
        target=blender,
        discovery=disc,
        snapshot=snapshot({arc: 9.0, nv: 97.0, amd: 1.0}, {arc: 3 * GIB, nv: int(8.1 * GIB), amd: 0}),
        observed=observed,
        preferred=interpret("SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;", disc),
        hotkey_text=hotkey,
    )
    w = OverlayWindow()
    w.apply_state(state)
    w.set_apps_open(True)
    nv_name = disc.by_key(nv).short_name
    arc_name = disc.by_key(arc).short_name
    rows = [
        AppListRow("blender", "Blender", f"uses {nv_name} · preferred {nv_name}", AppGroup.RUNNING, 97.0),
        AppListRow("editor", "Code Editor", f"uses {arc_name}", AppGroup.RUNNING, 4.0),
        AppListRow("browser", "Web Browser", f"uses {arc_name}", AppGroup.RUNNING, 2.0),
        AppListRow("game1", "Example Game", f"Steam · preferred {arc_name}", AppGroup.INSTALLED, 0.0),
        AppListRow("game2", "Another Game", "Epic", AppGroup.INSTALLED, 0.0),
        AppListRow("unity", "Unity Editor", f"preferred {arc_name}", AppGroup.SAVED, 0.0),
    ]
    w.apps_panel.set_scan_state(False, (37, 26))
    w.set_app_list(rows, "blender", True)
    w.fit_to_content()
    w.grab().save(str(args.out / "overlay-apps.png"))

    # 2) A game that ignores the Windows preference → honest status + optional game mode.
    game = TargetApp(
        1,
        5151,
        r"D:\Games\Example Game\Game.exe",
        "Example Game",
        "GameWindow",
        file_description="Example Game",
        started_at=2000.0,
    )
    pref_arc = interpret("SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;", disc)
    on_rtx = ObservedGpu(nv, Confidence.HIGH, (ProcessGpuSummary(nv, 99.0, 5 * GIB, {"3D": 99.0}),))
    offer = gamemode_offer(game, pref_arc, on_rtx, 1000.0, disc)
    state = build_state(
        target=game,
        discovery=disc,
        snapshot=snapshot({arc: 3.0, nv: 99.0, amd: 0.0}, {arc: 2 * GIB, nv: 6 * GIB, amd: 0}),
        observed=on_rtx,
        preferred=pref_arc,
        hotkey_text=hotkey,
        last_change_at=1000.0,
    )
    from gpucc.i18n import tr

    state = replace(
        state,
        gamemode_gpu=offer,
        gamemode_label=tr("🎮 Game mode: disable {gpu} while playing …", gpu=nv_name) if offer else "",
    )
    w2 = OverlayWindow()
    w2.apply_state(state)
    w2.fit_to_content()
    w2.grab().save(str(args.out / "overlay-game.png"))
    if args.lang == "en":
        _social_card(w.grab(), args.out / "social-card.png")
    print("written:", *(p.name for p in sorted(args.out.glob("*.png"))))
    app.quit()
    return 0


def _social_card(shot, path: Path) -> None:  # type: ignore[no-untyped-def]
    """1200×630 Open Graph image: icon, name, tagline and the overlay screenshot."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter

    from gpucc.branding import APP_NAME, TAGLINE
    from gpucc.ui.icons import app_pixmap

    img = QImage(1200, 630, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    bg = QLinearGradient(0, 0, 1200, 630)
    bg.setColorAt(0, QColor("#0F1115"))
    bg.setColorAt(1, QColor("#1B2333"))
    p.fillRect(img.rect(), bg)
    p.drawPixmap(64, 70, app_pixmap(96))
    title = QFont("Segoe UI", 44)
    title.setWeight(QFont.Weight.DemiBold)
    p.setFont(title)
    p.setPen(QColor("#E8EAED"))
    p.drawText(QRectF(64, 190, 560, 70), APP_NAME)
    body = QFont("Segoe UI", 21)
    p.setFont(body)
    p.setPen(QColor("#B8BEC6"))
    p.drawText(QRectF(64, 270, 520, 140), Qt.TextFlag.TextWordWrap, TAGLINE + ".")
    small = QFont("Segoe UI", 15)
    p.setFont(small)
    p.setPen(QColor("#7AA7FF"))
    p.drawText(QRectF(64, 490, 480, 80), "Free & open source · Windows 11\nNVIDIA · Intel Arc · AMD")
    scaled = shot.scaled(560, 540, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(1.0)  # grab() carries the screen's DPR; the card is laid out in real pixels
    p.drawPixmap(1200 - 48 - scaled.width(), (630 - scaled.height()) // 2, scaled)
    p.end()
    img.save(str(path))


if __name__ == "__main__":
    raise SystemExit(main())
