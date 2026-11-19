"""Right-hand analysis panel (ADR-0004): "Overview" (engines, VRAM, telemetry) and "Frames" (PresentMon)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gpucc.analysis.overview import ENGINE_GROUPS, WINDOWS_S, GpuTrend
from gpucc.analysis.presentmon import Frame, FrameStats
from gpucc.core.models import GpuKey
from gpucc.i18n import tr
from gpucc.ui.overlay.charts import SeriesChart
from gpucc.ui.overlay.colors import APP_COLOR
from gpucc.ui.overlay.viewmodel import de, fmt_bytes_short

ANALYSIS_WIDTH = 380
ENGINE_COLORS = {"3D": "#F2F3F5", "Compute": "#FFB454", "Copy": "#3DD6C6", "Video": "#C792FF"}
FRAME_COLOR = APP_COLOR
GPU_BUSY_COLOR = "#7AA7FF"
CHART_FRAMES = 300
_VERDICT_COLOR = {"gpu": "#9BD84A", "cpu": "#F2B33D", "mixed": "#9AA0A6"}


def _label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


def _button(text: str, name: str = "pin") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(name)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


def _set_active(button: QPushButton, active: bool) -> None:
    if button.property("active") != active:
        button.setProperty("active", active)
        button.style().unpolish(button)
        button.style().polish(button)


class _GpuSection(QWidget):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(3)
        self.name = _label()
        self.name.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.name)
        lay.addWidget(_label(tr("Engines of the application"), "subtle"))
        self.engines = SeriesChart(46)
        lay.addWidget(self.engines)
        legend = QHBoxLayout()
        legend.setSpacing(10)
        self.engine_labels: dict[str, QLabel] = {}
        for g in ENGINE_GROUPS:
            lbl = _label()
            lbl.setStyleSheet(f"color: {ENGINE_COLORS[g]}; font-size: 8.5pt;")
            legend.addWidget(lbl)
            self.engine_labels[g] = lbl
        legend.addStretch(1)
        lay.addLayout(legend)
        self.vram_title = _label(name="subtle")
        lay.addWidget(self.vram_title)
        self.vram = SeriesChart(34)
        lay.addWidget(self.vram)
        self.telemetry = _label(name="subtle")
        lay.addWidget(self.telemetry)

    def set_trend(self, trend: GpuTrend, name: str, color: str) -> None:
        self.name.setText(name)
        self.name.setStyleSheet(f"font-weight: 600; color: {color};")
        self.engines.set_data([(trend.engines[g], ENGINE_COLORS[g], g == "3D") for g in ENGINE_GROUPS], 100.0)
        for g in ENGINE_GROUPS:
            self.engine_labels[g].setText(f"▬ {g} {trend.engine_now[g]:.0f} %")
        peak = max((v for _, v in trend.vram), default=0.0)
        self.vram_title.setText(tr("Video memory of the application: {size}", size=fmt_bytes_short(trend.vram_now)))
        self.vram.set_data([(trend.vram, color, True)], peak * 1.15 if peak > 0 else 1.0)
        parts = []
        if trend.temperature_now is not None:
            parts.append(f"{trend.temperature_now:.0f} °C")
        if trend.power_now is not None:
            parts.append(f"{trend.power_now:.0f} W")
        self.telemetry.setText(tr("Graphics card now: {values}", values=" · ".join(parts)) if parts else "")
        self.telemetry.setVisible(bool(parts))


class AnalysisPanel(QFrame):
    window_changed = Signal(float)
    start_requested = Signal()
    stop_requested = Signal()
    grant_requested = Signal()
    export_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sideRight")
        self.setFixedWidth(ANALYSIS_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 16, 16)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label(tr("ANALYSIS"), "section"))
        head.addStretch(1)
        self.tab_overview = _button(tr("Overview"))
        self.tab_frames = _button(tr("Frames"))
        self.tab_overview.clicked.connect(lambda: self.show_tab(0))
        self.tab_frames.clicked.connect(lambda: self.show_tab(1))
        head.addWidget(self.tab_overview)
        head.addWidget(self.tab_frames)
        lay.addLayout(head)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_overview())
        self.pages.addWidget(self._build_frames())
        lay.addWidget(self.pages, 1)
        self.show_tab(0)

    # ------------------------------------------------------------------ overview
    def _build_overview(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.window_buttons: dict[float, QPushButton] = {}
        for seconds, text in zip(WINDOWS_S, ("30 s", "2 min", "5 min"), strict=True):
            b = _button(text)
            b.clicked.connect(lambda _c=False, s=seconds: self._choose_window(s))
            row.addWidget(b)
            self.window_buttons[seconds] = b
        row.addStretch(1)
        lay.addLayout(row)
        self.overview_hint = _label(name="subtle", wrap=True)
        lay.addWidget(self.overview_hint)
        self.sections_box = QVBoxLayout()
        self.sections_box.setSpacing(6)
        lay.addLayout(self.sections_box)
        lay.addStretch(1)
        self._sections: list[_GpuSection] = []
        self._choose_window(WINDOWS_S[0], emit=False)
        return page

    def _choose_window(self, seconds: float, emit: bool = True) -> None:
        self.window_s = seconds
        for s, b in self.window_buttons.items():
            _set_active(b, s == seconds)
        if emit:
            self.window_changed.emit(seconds)

    def set_overview(
        self,
        app_name: str | None,
        trends: Sequence[GpuTrend],
        names: Mapping[GpuKey, str],
        colors: Mapping[GpuKey, str],
    ) -> None:
        if app_name is None:
            hint = tr("Choose an application (left list or the active window) to analyse it.")
        elif not trends:
            hint = tr("{app} is not using a graphics card right now.", app=app_name)
        else:
            hint = ""
        self.overview_hint.setText(hint)
        self.overview_hint.setVisible(bool(hint))
        while len(self._sections) < len(trends):
            section = _GpuSection()
            self.sections_box.addWidget(section)
            self._sections.append(section)
        for i, section in enumerate(self._sections):
            if i < len(trends):
                t = trends[i]
                section.set_trend(t, names.get(t.key, "?"), colors.get(t.key, "#C8CCD2"))
            section.setVisible(i < len(trends))

    # ------------------------------------------------------------------ frames
    def _build_frames(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.frames_status = _label(name="subtle", wrap=True)
        lay.addWidget(self.frames_status)
        buttons = QHBoxLayout()
        self.start_button = _button(tr("▶ Start frame analysis"), "rescan")
        self.start_button.clicked.connect(self._on_start_stop)
        self.grant_button = _button(tr("Set up permission …"), "rescan")
        self.grant_button.clicked.connect(self.grant_requested)
        self.export_button = _button(tr("Save CSV …"))
        self.export_button.clicked.connect(self.export_requested)
        for b in (self.start_button, self.grant_button, self.export_button):
            buttons.addWidget(b)
        buttons.addStretch(1)
        lay.addLayout(buttons)
        self.verdict = _label(wrap=True)
        self.verdict.setStyleSheet("font-weight: 600;")
        lay.addWidget(self.verdict)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        self.values: dict[str, QLabel] = {}
        fields = (
            ("fps", tr("FPS")),
            ("low1", tr("1 % low")),
            ("low01", tr("0.1 % low")),
            ("frame", tr("Frame time")),
            ("gpu", tr("GPU busy")),
            ("latency", tr("Display latency")),
            ("dropped", tr("Not displayed")),
        )
        for i, (key, title) in enumerate(fields):
            grid.addWidget(_label(title, "key"), i // 2, (i % 2) * 2)
            value = _label()
            value.setStyleSheet("font-weight: 600;")
            grid.addWidget(value, i // 2, (i % 2) * 2 + 1)
            self.values[key] = value
        lay.addLayout(grid)
        self.mode_label = _label(name="subtle", wrap=True)
        lay.addWidget(self.mode_label)
        lay.addWidget(_label(tr("Frame times (last 300 frames)"), "subtle"))
        self.frame_chart = SeriesChart(90)
        self.frame_chart.setToolTip(tr("White: frame time. Blue: time the GPU was busy with the frame."))
        lay.addWidget(self.frame_chart)
        legend = QHBoxLayout()
        frame_legend = _label(tr("▬ frame time"))
        frame_legend.setStyleSheet(f"color: {FRAME_COLOR}; font-size: 8.5pt;")
        busy_legend = _label(tr("▬ GPU busy"))
        busy_legend.setStyleSheet(f"color: {GPU_BUSY_COLOR}; font-size: 8.5pt;")
        self.scale = _label(name="subtle")
        legend.addWidget(frame_legend)
        legend.addWidget(busy_legend)
        legend.addStretch(1)
        legend.addWidget(self.scale)
        lay.addLayout(legend)
        lay.addStretch(1)
        self._recording = False
        self.set_frames_state(status="", can_start=False, can_grant=False, recording=False, can_export=False)
        self.set_frame_stats(None, ())
        return page

    def _on_start_stop(self) -> None:
        (self.stop_requested if self._recording else self.start_requested).emit()

    def set_frames_state(
        self, *, status: str, can_start: bool, can_grant: bool, recording: bool, can_export: bool
    ) -> None:
        self._recording = recording
        self.frames_status.setText(status)
        self.frames_status.setVisible(bool(status))
        self.start_button.setText(tr("■ Stop") if recording else tr("▶ Start frame analysis"))
        self.start_button.setEnabled(recording or can_start)
        self.grant_button.setVisible(can_grant)
        self.export_button.setVisible(can_export and not recording)

    def set_frame_stats(self, s: FrameStats | None, recent: Sequence[Frame]) -> None:
        def ms(v: float | None) -> str:
            return f"{de(v)} ms" if v is not None else "–"

        if s is None:
            for v in self.values.values():
                v.setText("–")
            self.mode_label.setText("")
            self.verdict.setText("")
        else:
            self.values["fps"].setText(de(s.fps, 0))
            self.values["low1"].setText(de(s.low_1, 0))
            self.values["low01"].setText(de(s.low_01, 0))
            self.values["frame"].setText(ms(s.frame_ms))
            self.values["gpu"].setText(f"{s.gpu_busy_pct:.0f} %" if s.gpu_busy_pct is not None else "–")
            self.values["latency"].setText(ms(s.latency_ms))
            self.values["dropped"].setText(f"{s.dropped_pct:.0f} %")
            self.mode_label.setText(f"{tr('Present mode')}: {s.present_mode}" if s.present_mode else "")
            text = {
                "gpu": tr("GPU-limited – the graphics card is the bottleneck."),
                "cpu": tr("Not GPU-limited – the GPU waits (CPU, frame limiter or V-Sync)."),
                "mixed": tr("Balanced – neither clearly GPU- nor CPU-limited."),
            }.get(s.verdict, "")
            self.verdict.setText(text)
            self.verdict.setStyleSheet(f"font-weight: 600; color: {_VERDICT_COLOR.get(s.verdict, '#9AA0A6')};")
        frames = list(recent)[-CHART_FRAMES:]
        n = len(frames)
        if n >= 2:
            ordered = sorted(f.frame_ms for f in frames)
            top = max(16.7, ordered[min(n - 1, int(n * 0.99))] * 1.25)
            frame_pts = [(i / (n - 1), f.frame_ms) for i, f in enumerate(frames)]
            busy_pts = [(i / (n - 1), f.gpu_busy_ms) for i, f in enumerate(frames) if f.gpu_busy_ms is not None]
            self.frame_chart.set_data(
                [(busy_pts, GPU_BUSY_COLOR, True), (frame_pts, FRAME_COLOR, False)], top, guides=(16.7, 33.3)
            )
            self.scale.setText(tr("scale 0–{ms} ms · lines at 60/30 fps", ms=f"{top:.0f}"))
        else:
            self.frame_chart.set_data([], 33.3)
            self.scale.setText("")

    # ------------------------------------------------------------------ tabs
    def show_tab(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        _set_active(self.tab_overview, index == 0)
        _set_active(self.tab_frames, index == 1)
