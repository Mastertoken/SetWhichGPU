"""Spike S4: global hotkey + topmost overlay under real conditions.

Ctrl+Alt+G toggles an overlay on the monitor of the foreground window; Esc / focus loss closes it.
Every event is logged to stdout and build/s4_log.jsonl. Read-only, no registry access.
Usage: uv run python tools/spikes/s4_hotkey_overlay.py   (end via tray icon "Beenden")
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import wintypes as wt
from pathlib import Path

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QSystemTrayIcon, QVBoxLayout, QWidget

LOG = Path(__file__).resolve().parents[2] / "build" / "s4_log.jsonl"
LOG.parent.mkdir(exist_ok=True)

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32")
user32.GetForegroundWindow.restype = wt.HWND
user32.MonitorFromWindow.restype = wt.HANDLE
user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]

WM_HOTKEY = 0x0312
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x1, 0x2, 0x4000
HOTKEY_ID = 0xB001
QUNS = {1: "NOT_PRESENT", 2: "BUSY", 3: "RUNNING_D3D_FULL_SCREEN", 4: "PRESENTATION_MODE", 5: "ACCEPTS_NOTIFICATIONS", 6: "QUIET_TIME", 7: "APP"}


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD), ("szDevice", wt.WCHAR * 32)]


def log(event: str, **kw: object) -> None:
    rec = {"t": round(time.time(), 3), "event": event, **kw}
    line = json.dumps(rec, ensure_ascii=False)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def describe_window(hwnd: int) -> dict[str, object]:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, cls, 256)
    path, err = None, None
    h = kernel32.OpenProcess(0x1000, False, pid.value)
    if h:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            path = buf.value
        kernel32.CloseHandle(h)
    else:
        err = ctypes.get_last_error()
    state = ctypes.c_int()
    shell32.SHQueryUserNotificationState(ctypes.byref(state))
    mon = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mon))
    return {"hwnd": hwnd, "pid": pid.value, "title": title.value, "class": cls.value, "exe": path,
            "open_error": err, "notification_state": QUNS.get(state.value, state.value), "monitor": mon.szDevice,
            "monitor_origin": (mon.rcMonitor.left, mon.rcMonitor.top)}


class Overlay(QWidget):
    def __init__(self) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(440, 260)
        self.target: int | None = None
        self.shown_at = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        self.label = QLabel()
        self.label.setStyleSheet("color: #EDEDED;")
        self.label.setFont(QFont("Segoe UI", 10))
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay.addWidget(self.label)

    def paintEvent(self, _e: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        p.fillPath(path, QColor(24, 26, 30, 225))

    def toggle(self) -> None:
        if self.isVisible():
            self.close_overlay("hotkey")
            return
        t0 = time.perf_counter()
        fg = int(user32.GetForegroundWindow() or 0)
        info = describe_window(fg) if fg else {}
        self.target = fg or None
        # Qt names screens by monitor model; Qt 6 keeps the *native* top-left corner per screen,
        # so match on the physical monitor origin from GetMonitorInfoW.
        origin = info.get("monitor_origin")
        screen = next((s for s in QGuiApplication.screens() if (s.geometry().x(), s.geometry().y()) == origin), None)
        if screen is None:
            log("screen_match_failed", origin=origin)
            screen = QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self.label.setText(
            f"<b style='font-size:14pt'>{Path(str(info.get('exe') or '?')).name}</b><br>"
            f"{info.get('title', '')}<br><br>"
            f"PID {info.get('pid')} · Klasse {info.get('class')}<br>"
            f"Monitor {screen.name()} · DPR {screen.devicePixelRatio():.2f}<br>"
            f"Benachrichtigungsstatus: {info.get('notification_state')}<br><br>"
            f"<span style='color:#9AA0A6'>Esc / Strg+Alt+G schließt · Klick daneben schließt</span>"
        )
        self.show()
        self.raise_()
        self.activateWindow()
        fg_ok = bool(user32.SetForegroundWindow(int(self.winId())))
        self.shown_at = time.perf_counter()
        log("overlay_shown", target=info, screen=screen.name(), dpr=screen.devicePixelRatio(),
            set_foreground=fg_ok, show_ms=round((self.shown_at - t0) * 1000, 1))

    def close_overlay(self, reason: str) -> None:
        if not self.isVisible():
            return
        self.hide()
        restored = bool(user32.SetForegroundWindow(self.target)) if self.target else None
        log("overlay_closed", reason=reason, focus_restored=restored)

    def keyPressEvent(self, e: object) -> None:
        if e.key() == Qt.Key.Key_Escape:  # type: ignore[attr-defined]
            self.close_overlay("escape")

    def changeEvent(self, e: object) -> None:
        if self.isVisible() and not self.isActiveWindow() and time.perf_counter() - self.shown_at > 0.3:
            self.close_overlay("focus_lost")
        super().changeEvent(e)  # type: ignore[arg-type]


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, overlay: Overlay) -> None:
        super().__init__()
        self.overlay = overlay

    def nativeEventFilter(self, event_type: QByteArray | bytes, message: int) -> tuple[bool, int]:
        if bytes(event_type) == b"windows_generic_MSG":
            msg = wt.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                log("hotkey", foreground=int(user32.GetForegroundWindow() or 0))
                self.overlay.toggle()
                return True, 0
        return False, 0


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    overlay = Overlay()
    msg_window = QWidget()  # hidden receiver for WM_HOTKEY
    hwnd = int(msg_window.winId())
    ok = user32.RegisterHotKey(hwnd, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("G"))
    log("register_hotkey", ok=bool(ok), error=None if ok else ctypes.get_last_error(),
        screens=[{"name": s.name(), "dpr": s.devicePixelRatio(), "geom": s.geometry().getRect()} for s in app.screens()])
    filt = HotkeyFilter(overlay)
    app.installNativeEventFilter(filt)

    pm = QPixmap(32, 32)
    pm.fill(QColor("#3A7BFF"))
    tray = QSystemTrayIcon(QIcon(pm))
    menu = QMenu()
    act = QAction("S4 beenden")
    act.triggered.connect(app.quit)
    menu.addAction(act)
    tray.setContextMenu(menu)
    tray.setToolTip("GPU Control Center – Spike S4")
    tray.show()
    rc = app.exec()
    user32.UnregisterHotKey(hwnd, HOTKEY_ID)
    log("exit")
    return rc


if __name__ == "__main__":
    sys.exit(main())
