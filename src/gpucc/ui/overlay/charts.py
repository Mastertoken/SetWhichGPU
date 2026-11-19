"""Line charts with a fading area below (style of a download graph), used by the cards and the analysis panel."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

Points = Sequence[tuple[float, float]]  # x in 0..1, y in data units


class SeriesChart(QWidget):
    def __init__(self, height: int = 40) -> None:
        super().__init__()
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._series: list[tuple[tuple[tuple[float, float], ...], str, bool]] = []
        self._y_max = 100.0
        self._guides: tuple[float, ...] = ()

    def set_data(
        self, series: Sequence[tuple[Points, str, bool]], y_max: float = 100.0, guides: Sequence[float] = ()
    ) -> None:
        """series: (points, colour, fill area); guides: horizontal reference lines in data units."""
        self._series = [(tuple(p), c, f) for p, c, f in series]
        self._y_max = y_max if y_max > 0 else 1.0
        self._guides = tuple(guides)
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        top, bottom = 2.0, h - 1.5

        def y_of(v: float) -> float:
            return bottom - (bottom - top) * max(0.0, min(v, self._y_max)) / self._y_max

        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(0, int(bottom), int(w), int(bottom))
        dash = QPen(QColor(255, 255, 255, 30), 1)
        dash.setDashPattern([3, 4])
        p.setPen(dash)
        for g in self._guides:
            p.drawLine(0, int(y_of(g)), int(w), int(y_of(g)))
        for points, color, fill in self._series:
            if len(points) < 2:
                continue
            line = QPainterPath()
            for i, (x, v) in enumerate(points):
                pt = (x * w, y_of(v))
                if i == 0:
                    line.moveTo(*pt)
                else:
                    line.lineTo(*pt)
            base = QColor(color)
            if fill:
                area = QPainterPath(line)
                area.lineTo(points[-1][0] * w, bottom)
                area.lineTo(points[0][0] * w, bottom)
                area.closeSubpath()
                grad = QLinearGradient(0, top, 0, bottom)
                c = QColor(base)
                c.setAlpha(80)
                grad.setColorAt(0.0, c)
                c.setAlpha(0)
                grad.setColorAt(1.0, c)
                p.fillPath(area, grad)
            p.setPen(QPen(base, 1.6))
            p.drawPath(line)
        p.end()
