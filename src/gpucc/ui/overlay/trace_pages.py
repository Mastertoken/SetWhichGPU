"""Trace lanes and RenderDoc action inspection for analysis stages C and D."""

from __future__ import annotations

import zlib
from collections import defaultdict
from html import escape
from math import ulp

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gpucc.analysis.renderdoc import Capture
from gpucc.analysis.timeline import Interval, covered_us
from gpucc.i18n import tr

TRACE_WIDTH = 330
TEXT = QColor("#E8EAED")
SUBTLE = QColor("#9AA0A6")
VISIBLE_LIMIT = 2000
PROCESS_COLORS = ("#7AA7FF", "#FFB454", "#3DD6C6", "#C792FF", "#9BD84A", "#F39BB0")


def _accent_button(text: str) -> QPushButton:
    """Same accent style as the other panel buttons (#rescan in the overlay style sheet)."""
    button = QPushButton(text)
    button.setObjectName("rescan")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


def status(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setObjectName("subtle")
    return label


class TimelinePage(QWidget):
    import_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._rows: tuple[Interval, ...] = ()
        self._frames: dict[str, tuple[float, float]] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.note = status(tr("Import timestamped queue events or a profiler trace."))
        layout.addWidget(self.note)
        self.open_button = _accent_button(tr("Import trace…"))
        self.open_button.clicked.connect(self.import_requested)
        layout.addWidget(self.open_button)

        controls = QHBoxLayout()
        self.frame = QComboBox()
        self.frame.setAccessibleName(tr("Frame window"))
        self.frame.setMinimumContentsLength(8)
        self.frame.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.frame.addItem(tr("Entire trace"), "")
        self.frame.currentIndexChanged.connect(self._draw)
        controls.addWidget(self.frame, 1)
        self.zoom = QComboBox()
        self.zoom.setAccessibleName(tr("Timeline zoom"))
        for factor in (1, 4, 16, 64, 256, 1024):
            self.zoom.addItem(f"×{factor}", factor)
        self.zoom.currentIndexChanged.connect(self._draw)
        controls.addWidget(self.zoom)
        layout.addLayout(controls)
        self.offset = QSlider(Qt.Orientation.Horizontal)
        self.offset.setAccessibleName(tr("Timeline position"))
        self.offset.setRange(0, 10000)
        self.offset.valueChanged.connect(self._draw)
        layout.addWidget(self.offset)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Filter by queue, process or event"))
        self.search.textChanged.connect(self._draw)
        layout.addWidget(self.search)
        self.summary = status()
        layout.addWidget(self.summary)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.view, 1)

    def set_trace(self, rows: tuple[Interval, ...], source: str) -> None:
        self._rows = rows
        self._frames.clear()
        for row in rows:
            if row.frame:
                low, high = self._frames.get(row.frame, (row.start_us, row.end_us))
                self._frames[row.frame] = min(low, row.start_us), max(high, row.end_us)
        self._bounds = rows[0].start_us, max(row.end_us for row in rows)
        self.frame.blockSignals(True)
        self.frame.clear()
        self.frame.addItem(tr("Entire trace"), "")
        for frame in self._frames:
            self.frame.addItem(frame, frame)
        self.frame.blockSignals(False)
        self.note.setText(source)
        self._draw()

    def _text(self, text: str, x: int, y: int, color: QColor = TEXT) -> None:
        item = self.scene.addSimpleText(text)  # plain text – names from trace files are never rendered as HTML
        item.setBrush(QBrush(color))
        item.setPos(x, y)

    def _draw(self) -> None:
        if not self._rows:
            return
        low, high = self._frames.get(self.frame.currentData(), self._bounds)
        span = max((high - low) / int(self.zoom.currentData()), ulp(max(abs(low), abs(high))))
        span = min(span, high - low)
        self.offset.setEnabled(self.zoom.currentIndex() > 0)
        start = min(high - span, low + (high - low - span) * self.offset.value() / self.offset.maximum())
        end = min(high, start + span)
        span = end - start
        self.scene.clear()
        query = self.search.text().casefold().strip()
        tracks: dict[str, list[Interval]] = defaultdict(list)
        count = 0
        matches = 0
        for row in self._rows:
            if row.start_us >= end:
                break
            if row.end_us <= start or (query and query not in f"{row.track} {row.process} {row.name}".casefold()):
                continue
            matches += 1
            if count < VISIBLE_LIMIT:
                tracks[row.track].append(row)
                count += 1
        self.summary.setText(
            tr("Showing {shown} of {total} intervals · {ms} ms", shown=count, total=matches, ms=f"{span / 1000:.3f}")
        )
        y = 24
        self._text(f"{(start - low) / 1000:.3f} ms", 0, 0, SUBTLE)
        right_edge = f"{(end - low) / 1000:.3f} ms"
        right_label = self.scene.addSimpleText(right_edge)
        right_label.setBrush(QBrush(SUBTLE))
        right_label.setPos(TRACE_WIDTH - right_label.boundingRect().width(), 0)
        for track, rows in tracks.items():
            clipped = [(max(start, row.start_us), min(end, row.end_us)) for row in rows]
            coverage = covered_us(clipped) / span
            if matches > count:
                title = track
            else:
                title = tr("{track} · {pct}% interval coverage", track=track, pct=f"{coverage * 100:.0f}")
            self._text(title[:75], 0, y)
            y += 22
            lane_ends: list[float] = []
            for row, (left, right) in zip(rows, clipped, strict=True):
                lane = next((i for i, stop in enumerate(lane_ends) if stop <= left), len(lane_ends))
                if lane == len(lane_ends):
                    lane_ends.append(right)
                else:
                    lane_ends[lane] = right
                color = PROCESS_COLORS[zlib.crc32(row.process.encode("utf-8", "replace")) % len(PROCESS_COLORS)]
                bar = self.scene.addRect(
                    (left - start) * TRACE_WIDTH / span,
                    y + lane * 12,
                    max(1.0, (right - left) * TRACE_WIDTH / span),
                    10,
                    QPen(Qt.PenStyle.NoPen),
                    QBrush(QColor(color)),
                )
                bar.setToolTip(
                    "<qt>"
                    + escape(
                        f"{row.name}\n{row.process}\n{row.track}\n"
                        f"{(row.start_us - low) / 1000:.3f} ms → {(row.end_us - low) / 1000:.3f} ms"
                    ).replace("\n", "<br>")
                    + "</qt>"
                )
            y += 12 * len(lane_ends) + 8
        self.scene.setSceneRect(0, 0, TRACE_WIDTH + 4, max(y, 1))


class PassPage(QWidget):
    launch_requested = Signal()
    import_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.note = status(tr("Capture a frame in RenderDoc, then open its local capture file."))
        layout.addWidget(self.note)
        self.launch_button = _accent_button(tr("Open RenderDoc…"))
        self.launch_button.clicked.connect(self.launch_requested)
        layout.addWidget(self.launch_button)
        self.open_button = _accent_button(tr("Import capture…"))
        self.open_button.clicked.connect(self.import_requested)
        layout.addWidget(self.open_button)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Action or marker"), tr("GPU replay (ms)"), tr("Outputs")])
        self.tree.setColumnWidth(0, 160)
        self.tree.setColumnWidth(1, 95)
        self.tree.setUniformRowHeights(True)
        layout.addWidget(self.tree, 1)

    def set_capture(self, capture: Capture) -> None:
        self.tree.clear()
        self.note.setText(
            tr("{api} · {n} actions", api=capture.api, n=len(capture.actions))
            + (" · " + tr("Capture display limit reached") if capture.truncated else "")
        )
        parents: list[tuple[int, QTreeWidgetItem]] = []
        entries: list[tuple[QTreeWidgetItem, int, float | None]] = []
        for action in capture.actions:
            del parents[action.depth :]
            duration = f"{action.gpu_ms:.4f}" if action.gpu_ms is not None else "–"
            title = f"{action.event}  {action.name}"
            item = QTreeWidgetItem([title, duration, action.outputs])
            item.setToolTip(0, f"<qt>{escape(title)}<br>{escape(action.kind)}</qt>")
            item.setToolTip(2, f"<qt>{escape(action.outputs)}</qt>")
            if parents:
                parents[-1][1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            entries.append((item, parents[-1][0] if parents else -1, action.gpu_ms))
            parents.append((len(entries) - 1, item))
        descendants: dict[int, float] = defaultdict(float)
        for index in reversed(range(len(entries))):
            item, parent, measured = entries[index]
            if measured is None and index in descendants:
                measured = descendants[index]
                item.setText(1, f"Σ {measured:.4f}")
                item.setToolTip(1, tr("Σ descendant GPU action times, which may overlap."))
            if parent >= 0 and measured is not None:
                descendants[parent] += measured
        self.tree.expandToDepth(0)
