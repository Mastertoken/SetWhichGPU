"""System tray icon and menu."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from gpucc.branding import APP_NAME
from gpucc.i18n import tr


def make_icon() -> QIcon:
    """Small GPU-chip glyph drawn at several sizes (no binary assets needed)."""
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = size / 32
        p.setPen(QPen(QColor("#7AA7FF"), max(1.0, 2 * s)))
        for i in range(4):
            x = (8 + i * 5.3) * s
            p.drawLine(int(x), int(2 * s), int(x), int(30 * s))
            p.drawLine(int(2 * s), int(x), int(30 * s), int(x))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#1E2430"))
        p.drawRoundedRect(QRectF(5 * s, 5 * s, 22 * s, 22 * s), 4 * s, 4 * s)
        p.setBrush(QColor("#7AA7FF"))
        p.drawRoundedRect(QRectF(10 * s, 10 * s, 12 * s, 12 * s), 2 * s, 2 * s)
        p.end()
        icon.addPixmap(pm)
    return icon


class TrayService(QObject):
    open_overlay = Signal()
    rescan = Signal()
    open_logs = Signal()
    autostart_toggled = Signal(bool)
    revert_requested = Signal()
    quit_requested = Signal()
    gamemode_stop = Signal()
    language_chosen = Signal(str)  # "system" or a code from gpucc.i18n.SUPPORTED

    def __init__(self, hotkey_text: str, autostart_available: bool = True, language: str = "system") -> None:
        super().__init__()
        from gpucc.ui.icons import app_icon

        self.tray = QSystemTrayIcon(app_icon())
        self.tray.setToolTip(f"{APP_NAME} – {hotkey_text}")
        self._menu = QMenu()
        self._open = QAction(f"{tr('Open overlay')}\t{hotkey_text}")
        self._open.triggered.connect(self.open_overlay)
        self._rescan = QAction(tr("Rescan graphics cards and games"))
        self._rescan.triggered.connect(self.rescan)
        self._autostart = QAction(tr("Start with Windows"))
        self._autostart.setCheckable(True)
        self._autostart.setEnabled(autostart_available)
        self._autostart.toggled.connect(self.autostart_toggled)
        self._revert = QAction(tr("Reset GPU preferences …"))
        self._revert.triggered.connect(self.revert_requested)
        self._logs = QAction(tr("Open log folder"))
        self._logs.triggered.connect(self.open_logs)
        self._quit = QAction(tr("Quit"))
        self._quit.triggered.connect(self.quit_requested)
        self._gamemode = QAction("")
        self._gamemode.setVisible(False)
        self._gamemode.triggered.connect(self.gamemode_stop)
        for a in (self._gamemode, self._open, self._rescan):
            self._menu.addAction(a)
        self._menu.addSeparator()
        self._menu.addAction(self._autostart)
        self._language_menu = self._menu.addMenu(tr("Language"))
        self._language_group = QActionGroup(self)
        self._language_actions: dict[str, QAction] = {}
        # Language names stay in their own language so a user can always find theirs.
        for code, label in (
            ("system", tr("Windows language")),
            ("en", "English"),
            ("de", "Deutsch"),
            ("es", "Español"),
            ("fr", "Français"),
        ):
            action = QAction(label, self._language_group)
            action.setCheckable(True)
            action.setChecked(code == language)
            action.triggered.connect(lambda _checked=False, c=code: self.language_chosen.emit(c))
            self._language_menu.addAction(action)
            self._language_actions[code] = action
        for a in (self._revert, self._logs):
            self._menu.addAction(a)
        self._menu.addSeparator()
        self._menu.addAction(self._quit)
        self.tray.setContextMenu(self._menu)
        self.tray.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_overlay.emit()

    def set_gamemode(self, text: str | None) -> None:
        """Show 'End game mode …' while a session is active."""
        self._gamemode.setText(text or "")
        self._gamemode.setVisible(bool(text))

    def set_autostart_checked(self, checked: bool) -> None:
        """Reflect the real state without re-emitting autostart_toggled."""
        self._autostart.blockSignals(True)
        self._autostart.setChecked(checked)
        self._autostart.blockSignals(False)

    def set_language_checked(self, code: str) -> None:
        action = self._language_actions.get(code)
        if action is not None:
            action.setChecked(True)

    def show(self) -> None:
        self.tray.show()

    def notify(self, title: str, text: str, warning: bool = False) -> None:
        icon = QSystemTrayIcon.MessageIcon.Warning if warning else QSystemTrayIcon.MessageIcon.Information
        self.tray.showMessage(title, text, icon, 6000)

    def hide(self) -> None:
        self.tray.hide()
