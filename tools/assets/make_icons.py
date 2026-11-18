"""Generate app icons from src/gpucc/assets/icon-source.png (1024×1024).

Square crop around the card (less empty background → readable at 16 px), rounded corners,
PNGs in several sizes plus a multi-size .ico for installers.
Usage: uv run python tools/assets/make_icons.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QImageWriter, QPainter, QPainterPath

ASSETS = Path(__file__).resolve().parents[2] / "src" / "gpucc" / "assets"
SOURCE = ASSETS / "icon-source.png"
CROP = QRect(115, 130, 820, 820)  # card ≈ x 180–870, y 305–775 in the source
SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
CORNER = 0.18  # radius as fraction of the edge length


def rounded(img: QImage, size: int) -> QImage:
    scaled = img.scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * CORNER, size * CORNER)
    p.setClipPath(path)
    p.drawImage(0, 0, scaled)
    p.end()
    return out


def main() -> int:
    _app = QGuiApplication(sys.argv)
    src = QImage(str(SOURCE))
    if src.isNull():
        print(f"cannot read {SOURCE}")
        return 1
    square = src.copy(CROP)
    for size in SIZES:
        rounded(square, size).save(str(ASSETS / f"icon-{size}.png"))
    if b"ico" in [bytes(f.data()) for f in QImageWriter.supportedImageFormats()]:
        # Qt's ICO writer stores one image; installers can use the 256 px PNG-compressed entry.
        rounded(square, 256).save(str(ASSETS / "icon.ico"), "ICO")
    print("written:", ", ".join(sorted(p.name for p in ASSETS.glob("icon-*.png"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
