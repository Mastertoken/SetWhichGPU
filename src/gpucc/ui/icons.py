"""Application icon from the bundled assets (falls back to a drawn glyph if assets are missing)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap

ASSETS = Path(__file__).resolve().parents[1] / "assets"
ICON_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)

_cache: QIcon | None = None


def app_icon() -> QIcon:
    global _cache  # noqa: PLW0603 – icons are loaded once per process
    if _cache is not None:
        return _cache
    icon = QIcon()
    for size in ICON_SIZES:
        path = ASSETS / f"icon-{size}.png"
        if path.is_file():
            icon.addFile(str(path), QSize(size, size))
    if icon.isNull():
        from gpucc.ui.tray import make_icon

        icon = make_icon()
    _cache = icon
    return icon


def app_pixmap(size: int) -> QPixmap:
    return app_icon().pixmap(QSize(size, size))
