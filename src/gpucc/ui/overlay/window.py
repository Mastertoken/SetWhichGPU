"""Frameless, translucent, topmost overlay window. Renders an OverlayState; contains no logic."""

from __future__ import annotations

import html
import time
from collections.abc import Sequence

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QScreen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gpucc.branding import APP_NAME
from gpucc.core.models import GpuKey
from gpucc.i18n import tr
from gpucc.ui.icons import app_pixmap
from gpucc.ui.overlay.applist import AppGroup, AppListRow
from gpucc.ui.overlay.viewmodel import GpuRow, Level, OverlayState

WIDTH = 480
SIDE_WIDTH = 270
SCREEN_MARGIN = 8  # px kept free above and below when the overlay is as tall as the screen
BRAND_ICON_PX = 22
WHEEL_STEP_PX = 72  # one wheel notch
WHEEL_ANIM_MS = 180
WHEEL_IDLE_S = 1.5  # list counts as "being scrolled" this long after the last wheel event
RADIUS = 14
_ROLE_KEY = Qt.ItemDataRole.UserRole
_ROLE_SEARCH = Qt.ItemDataRole.UserRole + 1
_ROLE_HEADER = Qt.ItemDataRole.UserRole + 2
FOCUS_GRACE_S = 0.3

_LEVEL_COLOR = {Level.OK: "#4CC38A", Level.WARN: "#F2B33D", Level.MUTED: "#8A9099", Level.ERROR: "#F0605D"}

STYLE = """
QWidget { color: #E8EAED; font-family: 'Segoe UI'; font-size: 10pt; }
QLabel#title { font-size: 15pt; font-weight: 600; }
QLabel#brand { color: #B4E6D2; font-size: 9.5pt; font-weight: 600; letter-spacing: 0.5px; }
QLabel#subtle { color: #9AA0A6; font-size: 9pt; }
QLabel#section { color: #9AA0A6; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; }
QLabel#key { color: #9AA0A6; }
QLabel#badge { color: #0F1115; background: #9AA0A6; border-radius: 6px; padding: 0 6px;
               font-size: 8pt; font-weight: 600; }
QLabel#badgeUse { color: #0F1115; background: #4CC38A; border-radius: 6px; padding: 0 6px;
                  font-size: 8pt; font-weight: 600; }
QLabel#badgePref { color: #0F1115; background: #7AA7FF; border-radius: 6px; padding: 0 6px;
                   font-size: 8pt; font-weight: 600; }
QFrame#sep { background: rgba(255,255,255,0.08); max-height: 1px; min-height: 1px; border: none; }
QFrame#card { background: rgba(255,255,255,0.04); border-radius: 10px; border: 1px solid transparent; }
QFrame#card[selectable="true"]:hover { background: rgba(255,255,255,0.08); }
QFrame#card[selected="true"] { background: rgba(122,167,255,0.12); border: 1px solid #7AA7FF; }
QLabel#radio { color: #7AA7FF; font-size: 11pt; }
QFrame#side { background: rgba(255,255,255,0.035); border: none;
              border-right: 1px solid rgba(255,255,255,0.08);
              border-top-left-radius: 14px; border-bottom-left-radius: 14px; }
QLineEdit { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.08);
            border-radius: 8px; padding: 4px 8px; selection-background-color: #7AA7FF; }
QLineEdit:focus { border: 1px solid #7AA7FF; }
QListWidget#apps { background: transparent; border: none; outline: none; }
QListWidget#apps::item { border-radius: 8px; color: #9AA0A6; font-size: 8pt; font-weight: 600; }
QListWidget#apps::item:hover { background: rgba(255,255,255,0.06); }
QListWidget#apps::item:selected { background: rgba(122,167,255,0.18); }
QPushButton#follow { color: #E8EAED; background: rgba(122,167,255,0.18); border: 1px solid #7AA7FF;
                     border-radius: 8px; padding: 4px 8px; text-align: left; font-size: 9pt; }
QPushButton#follow:hover { background: rgba(122,167,255,0.28); }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.15); border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QPushButton#gamemode { color: #F2B33D; background: rgba(242,179,61,0.10); border: 1px solid rgba(242,179,61,0.45);
                       border-radius: 8px; padding: 5px 10px; text-align: left; }
QPushButton#gamemode:hover { background: rgba(242,179,61,0.20); }
QPushButton#apply { color: #0F1115; background: #7AA7FF; border: none; border-radius: 8px;
                    padding: 5px 16px; font-weight: 600; }
QPushButton#apply:hover { background: #9BBEFF; }
QPushButton#apply:disabled { color: #6B7078; background: rgba(255,255,255,0.06); }
QProgressBar { background: rgba(255,255,255,0.08); border: none; border-radius: 3px;
               max-height: 6px; min-height: 6px; }
QProgressBar::chunk { background: #7AA7FF; border-radius: 3px; }
QPushButton#pin { color: #9AA0A6; background: rgba(255,255,255,0.06); border: none;
                  border-radius: 8px; padding: 3px 10px; font-size: 8.5pt; }
QPushButton#pin:hover { background: rgba(255,255,255,0.12); color: #E8EAED; }
QPushButton#pin[active="true"] { color: #0F1115; background: #7AA7FF; font-weight: 600; }
"""


def _label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    lbl.setTextFormat(Qt.TextFormat.PlainText)
    return lbl


def _sep() -> QFrame:
    f = QFrame()
    f.setObjectName("sep")
    return f


class _ToggleHeader(QLabel):
    """Section header with ▸/▾ that expands or collapses the section below it on click."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("section")
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()  # no window drag
        else:
            super().mousePressEvent(event)


class _SelectableCard(QFrame):
    """Card that can act as a radio option. Click selects (never applies)."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("card")
        self.radio = _label("○", "radio")
        self._selectable = False

    def set_selection(self, selectable: bool, selected: bool) -> None:
        self._selectable = selectable
        self.radio.setVisible(selectable)
        self.radio.setText("●" if selected else "○")
        self.setCursor(Qt.CursorShape.PointingHandCursor if selectable else Qt.CursorShape.ArrowCursor)
        for prop, value in (("selectable", selectable), ("selected", selectable and selected)):
            if self.property(prop) != value:
                self.setProperty(prop, value)
                self.style().unpolish(self)
                self.style().polish(self)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._selectable and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)  # → window drag


class _DefaultCard(_SelectableCard):
    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(8)
        self.text = _label()
        lay.addWidget(self.radio)
        lay.addWidget(self.text, 1)


TOTAL_COLOR = "#7A86FF"  # whole GPU
APP_COLOR = "#E0559A"  # selected application
CHART_HEIGHT = 40


class _LoadChart(QWidget):
    """Load over the last 30 s as lines with a fading area below (whole GPU + selected app)."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(CHART_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._series: list[tuple[tuple[tuple[float, float], ...], str]] = []

    def set_series(self, total: Sequence[tuple[float, float]], app: Sequence[tuple[float, float]]) -> None:
        self._series = [(tuple(total), TOTAL_COLOR), (tuple(app), APP_COLOR)]
        self.update()

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        top, bottom = 2.0, h - 1.5
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawLine(0, int(bottom), int(w), int(bottom))  # baseline
        for points, color in self._series:
            if len(points) < 2:
                continue
            line = QPainterPath()
            for i, (x, v) in enumerate(points):
                pt = (x * w, bottom - (bottom - top) * v / 100.0)
                if i == 0:
                    line.moveTo(*pt)
                else:
                    line.lineTo(*pt)
            area = QPainterPath(line)
            area.lineTo(points[-1][0] * w, bottom)
            area.lineTo(points[0][0] * w, bottom)
            area.closeSubpath()
            base = QColor(color)
            grad = QLinearGradient(0, top, 0, bottom)
            fill = QColor(base)
            fill.setAlpha(80)
            grad.setColorAt(0.0, fill)
            fill.setAlpha(0)
            grad.setColorAt(1.0, fill)
            p.fillPath(area, grad)
            p.setPen(QPen(base, 1.6))
            p.drawPath(line)
        p.end()


class _GpuCard(_SelectableCard):
    def __init__(self) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 9)
        lay.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(self.radio)
        self.name = _label()
        self.name.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.badge = _label(name="badge")
        self.use = _label(tr("in use"), "badgeUse")
        self.pref = _label(tr("preferred"), "badgePref")
        self.util = _label()
        self.util.setStyleSheet(f"color: {TOTAL_COLOR}; font-weight: 600;")
        self.util.setToolTip(tr("Load of the whole graphics card – all applications together"))
        top.addWidget(self.name)
        top.addWidget(self.badge)
        top.addWidget(self.use)
        top.addWidget(self.pref)
        top.addStretch(1)
        top.addWidget(self.util)
        lay.addLayout(top)
        self.chart = _LoadChart()
        self.chart.setToolTip(
            tr("Last 30 seconds. Blue: whole graphics card (all applications). Pink: the selected application.")
        )
        lay.addWidget(self.chart)
        legend = QHBoxLayout()
        legend.setSpacing(10)
        self.app_share = _label()
        self.app_share.setStyleSheet(f"color: {APP_COLOR}; font-size: 9pt; font-weight: 600;")
        self.app_share.setToolTip(tr("Share of the selected application in this graphics card's load"))
        self.metrics = _label(name="subtle")
        self.span = _label(tr("last 30 s"), "subtle")
        legend.addWidget(self.app_share)
        legend.addWidget(self.metrics)
        legend.addStretch(1)
        legend.addWidget(self.span)
        lay.addLayout(legend)

    def set_row(self, row: GpuRow) -> None:
        self.name.setText(row.name)
        self.badge.setText(row.badge)
        self.badge.setVisible(bool(row.badge))
        self.use.setVisible(row.used_by_target)
        self.pref.setVisible(row.preferred)
        self.util.setText(row.util_text)
        self.chart.set_series(row.total_series, row.app_series)
        self.app_share.setText(f"▬ {row.app_text}" if row.app_text else "")
        self.app_share.setVisible(bool(row.app_text))
        self.metrics.setText("   ".join(p for p in (row.vram_text, row.temp_text, row.power_text) if p))


class _SmoothWheel(QObject):
    """Animated mouse-wheel scrolling for a scroll area (touchpads keep native pixel scrolling)."""

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._bar = area.verticalScrollBar()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(WHEEL_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: self._bar.setValue(round(float(v))))
        self._target = 0
        self._last_wheel = 0.0

    def recently_used(self) -> bool:
        return (
            self._anim.state() == QAbstractAnimation.State.Running or time.monotonic() - self._last_wheel < WHEEL_IDLE_S
        )

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel or not isinstance(event, QWheelEvent):
            return False
        self._last_wheel = time.monotonic()
        if not event.pixelDelta().isNull():
            return False  # precise touchpad delta → let Qt scroll pixel by pixel
        steps = event.angleDelta().y() / 120
        if not steps:
            return False
        running = self._anim.state() == QAbstractAnimation.State.Running
        base = self._target if running else self._bar.value()
        self._target = max(self._bar.minimum(), min(self._bar.maximum(), round(base - steps * WHEEL_STEP_PX)))
        self._anim.stop()
        self._anim.setStartValue(self._bar.value())
        self._anim.setEndValue(self._target)
        self._anim.start()
        return True


class _AppPanel(QFrame):
    """Collapsible list of applications (running, background, saved)."""

    app_selected = Signal(str)
    follow_requested = Signal()
    rescan_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("side")
        self.setFixedWidth(SIDE_WIDTH)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 12, 16)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_label(tr("APPLICATIONS"), "section"))
        head.addStretch(1)
        self.rescan_button = QPushButton(tr("⟳ Rescan"))
        self.rescan_button.setObjectName("pin")
        self.rescan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rescan_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rescan_button.setToolTip(tr("Rescan installed games and running applications (F5)"))
        self.rescan_button.clicked.connect(self.rescan_requested)
        head.addWidget(self.rescan_button)
        lay.addLayout(head)
        self.scan_status = _label(name="subtle")
        lay.addWidget(self.scan_status)
        self.follow_button = QPushButton(tr("↺  Follow active application"))
        self.follow_button.setObjectName("follow")
        self.follow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.follow_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.follow_button.clicked.connect(self.follow_requested)
        lay.addWidget(self.follow_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Search …"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("apps")
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # The main column decides the window height; the list just fills it.
        self.list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.list.itemClicked.connect(self._on_item)
        self.list.itemActivated.connect(self._on_item)
        self._wheel = _SmoothWheel(self.list)
        self.list.viewport().installEventFilter(self._wheel)
        self.list.installEventFilter(self)
        lay.addWidget(self.list, 1)
        self._signature: tuple[tuple[AppGroup, str], ...] = ()
        self._labels: dict[str, tuple[QListWidgetItem, QLabel, str]] = {}
        self._current: str | None = None
        self._pending: tuple[tuple[AppListRow, ...], str | None] | None = None

    def set_scan_state(self, scanning: bool, counts: tuple[int, int] | None) -> None:
        """counts = (games, programs) of the last finished scan."""
        self.rescan_button.setEnabled(not scanning)
        self.rescan_button.setText(tr("⟳ Scanning …") if scanning else tr("⟳ Rescan"))
        if scanning:
            self.scan_status.setText(tr("Scanning installed programs and games …"))
        elif counts is not None:
            self.scan_status.setText(tr("{apps} programs · {games} games found", apps=counts[1], games=counts[0]))
        self.scan_status.setVisible(scanning or counts is not None)

    # ------------------------------------------------------------------ updates
    def set_rows(self, rows: Sequence[AppListRow], current_key: str | None, following: bool) -> None:
        """Refresh without disturbing scrolling: texts update in place, re-ordering waits for the user."""
        self.follow_button.setVisible(not following)
        rows = tuple(rows)
        signature = tuple((r.group, r.key) for r in rows)
        if signature == self._signature:
            self._update_in_place(rows, current_key)
            self._pending = None
        elif self._user_is_scrolling():
            self._pending = (rows, current_key)  # applied when the mouse leaves the list
        else:
            self._rebuild(rows, current_key)
            self._pending = None

    def _user_is_scrolling(self) -> bool:
        return bool(self._signature) and (self.list.underMouse() or self._wheel.recently_used())

    @staticmethod
    def _html(row: AppListRow) -> str:
        sub = f"<div style='color:#9AA0A6; font-size:8.5pt'>{html.escape(row.subtitle)}</div>" if row.subtitle else ""
        return f"<div style='font-weight:600'>{html.escape(row.title)}</div>{sub}"

    def _update_in_place(self, rows: tuple[AppListRow, ...], current_key: str | None) -> None:
        for row in rows:
            item, label, old = self._labels[row.key]
            text = self._html(row)
            if text != old:
                label.setText(text)
                item.setData(_ROLE_SEARCH, f"{row.title} {row.key}".lower())
                item.setSizeHint(QSize(SIDE_WIDTH - 40, label.sizeHint().height() + 2))
                self._labels[row.key] = (item, label, text)
        self._select(current_key)

    def _rebuild(self, rows: tuple[AppListRow, ...], current_key: str | None) -> None:
        scroll = self.list.verticalScrollBar().value()
        self.list.setUpdatesEnabled(False)
        self.list.clear()
        self._labels = {}
        group = None
        for row in rows:
            if row.group != group:
                group = row.group
                header = QListWidgetItem(group.label.upper())
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                header.setData(_ROLE_HEADER, group.value)
                self.list.addItem(header)
            item = QListWidgetItem()
            item.setData(_ROLE_KEY, row.key)
            item.setData(_ROLE_SEARCH, f"{row.title} {row.key}".lower())
            text = self._html(row)
            label = QLabel(text)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setContentsMargins(8, 4, 6, 4)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            item.setSizeHint(QSize(SIDE_WIDTH - 40, label.sizeHint().height() + 2))
            self.list.addItem(item)
            self.list.setItemWidget(item, label)
            self._labels[row.key] = (item, label, text)
        self._signature = tuple((r.group, r.key) for r in rows)
        self._current = None
        self._select(current_key)
        self._apply_filter(self.search.text())
        self.list.verticalScrollBar().setValue(scroll)
        self.list.setUpdatesEnabled(True)

    def _select(self, key: str | None) -> None:
        if key == self._current:
            return
        self._current = key
        self.list.clearSelection()
        entry = self._labels.get(key) if key else None
        if entry is not None:
            entry[0].setSelected(True)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.list and event.type() == QEvent.Type.Leave and self._pending is not None:
            rows, current = self._pending
            self._pending = None
            self._rebuild(rows, current)
        return False

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        visible_groups: set[str] = set()
        group_items: list[tuple[QListWidgetItem, str]] = []
        current_group = ""
        for i in range(self.list.count()):
            item = self.list.item(i)
            header = item.data(_ROLE_HEADER)
            if header:
                current_group = str(header)
                group_items.append((item, current_group))
                continue
            hidden = bool(needle) and needle not in str(item.data(_ROLE_SEARCH))
            item.setHidden(hidden)
            if not hidden:
                visible_groups.add(current_group)
        for item, group in group_items:
            item.setHidden(group not in visible_groups)

    def _on_item(self, item: QListWidgetItem) -> None:
        key = item.data(_ROLE_KEY)
        if key:
            self.app_selected.emit(str(key))


class OverlayWindow(QWidget):
    """Transient by default (closes on focus loss). Pinned: stays visible while the user works."""

    closed = Signal(str)  # reason
    pinned_changed = Signal(bool)
    apply_requested = Signal(object)  # GpuKey | None (None = Windows-Standard)
    app_selected = Signal(str)  # app key from the side panel
    follow_requested = Signal()
    rescan_requested = Signal()
    apps_panel_toggled = Signal(bool)
    gamemode_requested = Signal(object)  # GpuKey to disable while the game runs

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(STYLE)
        self.setFixedWidth(WIDTH)
        self._apps_open = False
        self._shown_at = 0.0
        self._show_processes = False
        self._pinned = False
        self._drag_offset: QPoint | None = None
        self._positions: dict[str, QPoint] = {}  # screen name → user-chosen position (session only)
        self._screen_name = ""
        self._cards: dict[GpuKey, _GpuCard] = {}
        self._state: OverlayState | None = None
        self._selection: GpuKey | None = None  # None = Windows-Standard
        self._touched = False  # user changed the selection since the last apply / target switch
        self._selection_target: tuple[str, str] | None = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.apps_panel = _AppPanel()
        self.apps_panel.setVisible(False)
        self.apps_panel.app_selected.connect(self.app_selected)
        self.apps_panel.follow_requested.connect(self.follow_requested)
        self.apps_panel.rescan_requested.connect(self.rescan_requested)
        outer.addWidget(self.apps_panel)
        main = QWidget()
        main.setFixedWidth(WIDTH)
        outer.addWidget(main)
        root = QVBoxLayout(main)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(8)
        self.brand_icon = QLabel()
        self.brand_icon.setPixmap(app_pixmap(BRAND_ICON_PX))
        self.brand_icon.setFixedSize(BRAND_ICON_PX, BRAND_ICON_PX)
        self.brand_icon.setScaledContents(True)
        brand.addWidget(self.brand_icon)
        brand.addWidget(_label(APP_NAME, "brand"))
        brand.addStretch(1)
        root.addLayout(brand)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.title = _label(name="title")
        self.subtitle = _label(name="subtle")
        self.details = _label(name="subtle")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        titles.addWidget(self.details)
        head.addLayout(titles, 1)
        right = QVBoxLayout()
        right.setSpacing(4)
        self.hotkey = _label(name="subtle")
        self.hotkey.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.pin_button = QPushButton()
        self.pin_button.setObjectName("pin")
        self.pin_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pin_button.clicked.connect(self.toggle_pinned)
        self.apps_button = QPushButton(tr("☰ Applications"))
        self.apps_button.setObjectName("pin")
        self.apps_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apps_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apps_button.clicked.connect(self.toggle_apps_panel)
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.apps_button)
        buttons.addWidget(self.pin_button)
        right.addWidget(self.hotkey)
        right.addLayout(buttons)
        right.addStretch(1)
        head.addLayout(right)
        root.addLayout(head)

        self.status_block = QWidget()
        grid = QGridLayout(self.status_block)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        self.observed = _label(wrap=True)
        self.preferred = _label(wrap=True)
        self.status = _label(wrap=True)
        grid.addWidget(_label(tr("Uses"), "key"), 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.observed, 0, 1)
        grid.addWidget(_label(tr("Preference"), "key"), 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.preferred, 1, 1)
        grid.addWidget(_label(tr("Status"), "key"), 2, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.status, 2, 1)
        grid.setColumnStretch(1, 1)
        root.addWidget(_sep())
        root.addWidget(self.status_block)
        self.gamemode_button = QPushButton()
        self.gamemode_button.setObjectName("gamemode")
        self.gamemode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gamemode_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.gamemode_button.setVisible(False)
        self.gamemode_button.clicked.connect(self._on_gamemode_clicked)
        root.addWidget(self.gamemode_button)

        # Loaded models of local AI runtimes (ADR-0003). Their names come from other programs → plain text only.
        self.ai_header = _label(name="section")
        self.ai_label = _label(wrap=True)
        self.ai_label.setTextFormat(Qt.TextFormat.PlainText)
        for w in (self.ai_header, self.ai_label):
            w.setVisible(False)
            root.addWidget(w)

        root.addWidget(_sep())
        self.cards_header = _label(tr("GRAPHICS CARDS"), "section")
        root.addWidget(self.cards_header)
        self.default_card = _DefaultCard()
        self.default_card.clicked.connect(lambda: self.select(None))
        root.addWidget(self.default_card)
        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(6)
        root.addLayout(self.cards_box)

        self.apply_row = QWidget()
        apply_lay = QHBoxLayout(self.apply_row)
        apply_lay.setContentsMargins(0, 2, 0, 0)
        self.apply_hint = _label(name="subtle", wrap=True)
        self.apply_button = QPushButton(tr("Apply"))
        self.apply_button.setObjectName("apply")
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.apply_button.clicked.connect(self.request_apply)
        apply_lay.addWidget(self.apply_hint, 1)
        apply_lay.addWidget(self.apply_button)
        root.addWidget(self.apply_row)

        self.proc_header = _ToggleHeader()
        self.proc_header.setToolTip(tr("Show or hide per-GPU usage (P)"))
        self.proc_header.clicked.connect(self.toggle_processes)
        root.addWidget(self.proc_header)
        self.proc_label = _label(name="subtle", wrap=True)
        root.addWidget(self.proc_label)

        self.notes = _label(name="subtle", wrap=True)
        root.addWidget(self.notes)
        self.footer = _label(name="subtle")
        root.addWidget(self.footer)
        self._update_pin_ui()

    # ------------------------------------------------------------------ apps side panel
    @property
    def apps_open(self) -> bool:
        return self._apps_open

    def toggle_apps_panel(self) -> None:
        self.set_apps_open(not self._apps_open)

    def set_apps_open(self, open_: bool) -> None:
        if open_ == self._apps_open:
            return
        self._apps_open = open_
        # The panel opens to the left so the main content stays where it is (clamped to the screen).
        screen = self.screen().availableGeometry() if self.screen() else None
        x = self.x() - SIDE_WIDTH if open_ else self.x() + SIDE_WIDTH
        self.apps_panel.setVisible(open_)
        self.setFixedWidth(WIDTH + (SIDE_WIDTH if open_ else 0))
        if screen is not None and self.isVisible():
            x = max(screen.left(), min(x, screen.right() - self.width()))
            self.move(x, self.y())
        self.apps_button.setProperty("active", open_)
        self.apps_button.style().unpolish(self.apps_button)
        self.apps_button.style().polish(self.apps_button)
        self.fit_to_content()
        self.apps_panel_toggled.emit(open_)
        if open_:
            self.apps_panel.search.setFocus()

    def set_app_list(self, rows: Sequence[AppListRow], current_key: str | None, following: bool) -> None:
        self.apps_panel.set_rows(rows, current_key, following)

    # ------------------------------------------------------------------ pinning
    @property
    def pinned(self) -> bool:
        return self._pinned

    def set_pinned(self, pinned: bool) -> None:
        if pinned == self._pinned:
            return
        self._pinned = pinned
        self._update_pin_ui()
        self.pinned_changed.emit(pinned)

    def toggle_pinned(self) -> None:
        self.set_pinned(not self._pinned)

    def _update_pin_ui(self) -> None:
        self.pin_button.setText(tr("📌 Pinned") if self._pinned else tr("📌 Pin"))
        self.pin_button.setProperty("active", self._pinned)
        self.pin_button.style().unpolish(self.pin_button)
        self.pin_button.style().polish(self.pin_button)
        self.footer.setText(
            tr("Pinned · A unpin · L applications · ↑/↓ + Enter choose GPU · Esc closes")
            if self._pinned
            else tr("Esc closes · A pin · L applications · ↑/↓ + Enter GPU · P processes")
        )
        self._update_opacity()

    def _update_opacity(self) -> None:
        self.setWindowOpacity(0.82 if self._pinned and not self.isActiveWindow() else 1.0)

    # ------------------------------------------------------------------ rendering
    def apply_state(self, state: OverlayState) -> None:  # not "render": shadows QWidget.render
        fm = QFontMetrics(self.subtitle.font())
        self.title.setText(state.title)
        self.subtitle.setText(fm.elidedText(state.subtitle, Qt.TextElideMode.ElideMiddle, self._subtitle_width()))
        self.subtitle.setToolTip(state.subtitle)
        self.details.setText(state.details)
        self.details.setVisible(bool(state.details))
        self.hotkey.setText(state.hotkey_text)

        self.status_block.setVisible(state.has_target)
        self.gamemode_button.setVisible(state.gamemode_gpu is not None)
        self.gamemode_button.setText(state.gamemode_label)
        show_ai = state.has_target and bool(state.ai_title)
        self.ai_header.setText(state.ai_title)
        self.ai_label.setText("\n".join(state.ai_lines))
        self.ai_header.setVisible(show_ai)
        self.ai_label.setVisible(show_ai)
        for lbl, text, level in (
            (self.observed, state.observed_text, state.observed_level),
            (self.preferred, state.preferred_text, state.preferred_level),
            (self.status, state.status_text, state.status_level),
        ):
            lbl.setText(f"●  {text}")
            lbl.setStyleSheet(f"color: {_LEVEL_COLOR[level]};" if level is not Level.MUTED else "")

        keys = [r.key for r in state.gpus]
        if keys != list(self._cards):
            for card in self._cards.values():
                card.deleteLater()
            self._cards = {}
            for k in keys:
                card = _GpuCard()
                card.clicked.connect(lambda k=k: self.select(k))
                self.cards_box.addWidget(card)
                self._cards[k] = card
        for row in state.gpus:
            self._cards[row.key].set_row(row)

        # Selection follows the stored preference until the user picks something else.
        identity = (state.title, state.subtitle)
        if identity != self._selection_target or not self._touched:
            self._selection_target = identity
            self._selection = state.current_choice
            self._touched = False
        self._state = state
        self._update_selection_ui()

        show_procs = state.has_target and bool(state.processes)
        self._update_proc_header()
        self.proc_header.setVisible(show_procs)
        self.proc_label.setVisible(show_procs and self._show_processes)
        self.proc_label.setText(
            "\n".join(f"{p.gpu_name}: {p.activity_text} · VRAM {p.vram_text}" for p in state.processes)
        )
        self.notes.setText("\n".join(state.notes))
        self.notes.setVisible(bool(state.notes))
        self.fit_to_content()

    def fit_to_content(self) -> None:
        """Height that fits the content. QWidget.adjustSize() caps windows at 2/3 of the screen height,
        which squeezed the GPU cards when the status text wrapped onto several lines."""
        layout = self.layout()
        if layout is not None:
            layout.activate()
        height = self.heightForWidth(self.width()) if self.hasHeightForWidth() else -1
        height = max(height, self.minimumSizeHint().height())
        screen = self.screen()
        area = screen.availableGeometry() if screen is not None else None
        if area is not None:
            height = min(height, area.height() - 2 * SCREEN_MARGIN)
        self.resize(self.width(), height)
        if area is not None and self.isVisible() and self.y() + height > area.bottom() - SCREEN_MARGIN:
            # Grown while open (longer status, process list): slide up instead of leaving the screen.
            self.move(self.x(), max(area.top() + SCREEN_MARGIN, area.bottom() - SCREEN_MARGIN - height))

    def _subtitle_width(self) -> int:
        """Room left of the button column (its width depends on the language), so eliding never clips."""
        buttons = self.apps_button.sizeHint().width() + self.pin_button.sizeHint().width() + 6
        spacing = 16  # layout spacing between the title column and the buttons + safety margin
        return max(120, WIDTH - 2 * 20 - buttons - spacing)

    def _on_gamemode_clicked(self) -> None:
        if self._state is not None and self._state.gamemode_gpu is not None:
            self.gamemode_requested.emit(self._state.gamemode_gpu)

    # ------------------------------------------------------------------ selection
    def _options(self) -> list[GpuKey | None]:
        if self._state is None or not self._state.can_assign:
            return []
        return [None, *(r.key for r in self._state.gpus if r.assignable)]

    @property
    def selection(self) -> GpuKey | None:
        return self._selection

    @property
    def can_apply(self) -> bool:
        s = self._state
        return s is not None and s.can_assign and self._touched and self._selection != s.current_choice

    def select(self, choice: GpuKey | None) -> None:
        if choice not in self._options():
            return
        self._selection = choice
        self._touched = True
        self._update_selection_ui()

    def _move_selection(self, step: int) -> None:
        options = self._options()
        if not options:
            return
        idx = options.index(self._selection) if self._selection in options else 0
        self.select(options[(idx + step) % len(options)])

    def request_apply(self) -> None:
        if self.can_apply:
            self.apply_requested.emit(self._selection)

    def mark_applied(self) -> None:
        """Called by the controller after a successful write; selection follows the new preference."""
        self._touched = False

    def _update_selection_ui(self) -> None:
        s = self._state
        active = s is not None and s.has_target
        selectable = s is not None and s.can_assign
        self.cards_header.setText(tr("GPU FOR THIS APPLICATION") if active else tr("GRAPHICS CARDS"))
        self.default_card.setVisible(active)
        self.apply_row.setVisible(active)
        if s is None:
            return
        self.default_card.text.setText(s.default_label)
        self.default_card.set_selection(selectable, self._selection is None)
        for row in s.gpus:
            card = self._cards.get(row.key)
            if card is not None:
                card.set_selection(selectable and row.assignable, self._selection == row.key)
        self.apply_button.setEnabled(self.can_apply)
        if not selectable:
            self.apply_hint.setText(s.assign_reason)
        elif self.can_apply:
            self.apply_hint.setText(tr("Takes effect the next time the application starts."))
        else:
            self.apply_hint.setText(tr("Choose a GPU (click or ↑/↓) and apply (Enter)."))

    def toggle_processes(self) -> None:
        self._show_processes = not self._show_processes
        self.proc_label.setVisible(self._show_processes and self.proc_header.isVisible())
        self._update_proc_header()
        self.fit_to_content()

    def _update_proc_header(self) -> None:
        arrow = "▾" if self._show_processes else "▸"
        self.proc_header.setText(f"{tr('GPU USAGE OF THE APPLICATION')} {arrow}")

    # ------------------------------------------------------------------ show / hide
    def show_on(self, screen: QScreen) -> None:
        self.fit_to_content()
        self._screen_name = screen.name()
        g = screen.availableGeometry()
        remembered = self._positions.get(self._screen_name)
        if remembered is not None and g.contains(remembered):
            self.move(remembered)
        else:
            self.move(g.center().x() - self.width() // 2, g.top() + max(40, (g.height() - self.height()) // 3))
        self._shown_at = time.monotonic()
        self.show()
        self.raise_()
        self.activateWindow()

    def dismiss(self, reason: str) -> None:
        if self.isVisible():
            self.hide()
            self.set_pinned(False)
            self.closed.emit(reason)

    # ------------------------------------------------------------------ dragging
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            self._positions[self._screen_name] = self.pos()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event: QPaintEvent) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), RADIUS, RADIUS)
        p.fillPath(path, QColor(20, 22, 27, 232))
        p.setPen(QColor(255, 255, 255, 28))
        p.drawPath(path)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss("escape")
        elif event.key() == Qt.Key.Key_A:
            self.toggle_pinned()
        elif event.key() == Qt.Key.Key_L:
            self.toggle_apps_panel()
        elif event.key() == Qt.Key.Key_F5:
            self.set_apps_open(True)
            if self.apps_panel.rescan_button.isEnabled():
                self.rescan_requested.emit()
        elif event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._move_selection(-1 if event.key() == Qt.Key.Key_Up else 1)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.request_apply()
        elif event.key() == Qt.Key.Key_P:
            self.toggle_processes()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange and self.isVisible():
            self._update_opacity()
            if not self._pinned and not self.isActiveWindow() and time.monotonic() - self._shown_at > FOCUS_GRACE_S:
                self.dismiss("focus_lost")
        super().changeEvent(event)
