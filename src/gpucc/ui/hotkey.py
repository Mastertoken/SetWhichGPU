"""Global hotkey + app-level window messages via a hidden message window."""

from __future__ import annotations

import logging
from ctypes import wintypes as wt

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray, QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from gpucc.core.hotkey import MOD_NOREPEAT, Hotkey
from gpucc.platform.win32 import user32

log = logging.getLogger(__name__)

MESSAGE_WINDOW_TITLE = "SetWhichGPU.MessageWindow"
HOTKEY_ID = 0xB001
HARDWARE_DEBOUNCE_MS = 2000


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, service: HotkeyService) -> None:
        super().__init__()
        self._service = service

    def nativeEventFilter(
        self, event_type: QByteArray | bytes | bytearray | memoryview, message: int
    ) -> tuple[bool, int]:
        raw = event_type.data() if isinstance(event_type, QByteArray) else bytes(event_type)
        if raw != b"windows_generic_MSG":
            return False, 0
        msg = wt.MSG.from_address(int(message))
        if int(msg.hWnd or 0) != self._service.hwnd and msg.message != user32.WM_HOTKEY:
            return False, 0
        if msg.message == user32.WM_HOTKEY and msg.wParam == HOTKEY_ID:
            self._service.hotkey_pressed.emit()
            return True, 0
        if msg.message == user32.WM_APP_SHOW_OVERLAY:
            self._service.show_requested.emit()
            return True, 0
        if msg.message == user32.WM_APP_QUIT:
            self._service.quit_requested.emit()
            return True, 0
        if msg.message in (user32.WM_DISPLAYCHANGE, user32.WM_DEVICECHANGE):
            self._service.debounce.start()
        return False, 0


class HotkeyService(QObject):
    hotkey_pressed = Signal()
    show_requested = Signal()  # second instance asked us to show the overlay
    quit_requested = Signal()  # uninstaller asked us to exit
    hardware_changed = Signal()  # debounced WM_DISPLAYCHANGE / WM_DEVICECHANGE

    def __init__(self) -> None:
        super().__init__()
        self._window = QWidget()
        self._window.setWindowTitle(MESSAGE_WINDOW_TITLE)
        self.hwnd = int(self._window.winId())  # creates the native (never shown) window
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(HARDWARE_DEBOUNCE_MS)
        self.debounce.timeout.connect(self.hardware_changed)
        self._filter = _Filter(self)
        self._registered = False

    @property
    def native_filter(self) -> QAbstractNativeEventFilter:
        return self._filter

    def register(self, hotkey: Hotkey) -> int:
        """0 on success, else Win32 error (1409 = already registered by another app)."""
        self.unregister()
        err = user32.register_hotkey(self.hwnd, HOTKEY_ID, hotkey.modifiers | MOD_NOREPEAT, hotkey.vk)
        self._registered = err == 0
        log.info("hotkey registration", extra={"fields": {"hotkey": str(hotkey), "error": err}})
        return err

    def unregister(self) -> None:
        if self._registered:
            user32.unregister_hotkey(self.hwnd, HOTKEY_ID)
            self._registered = False


def notify_running_instance() -> bool:
    """Ask an already running instance to show its overlay."""
    hwnd = user32.find_window(MESSAGE_WINDOW_TITLE)
    return bool(hwnd) and user32.post_message(hwnd, user32.WM_APP_SHOW_OVERLAY)


def ask_running_instance_to_quit() -> bool:
    """Ask an already running instance to exit (it ends game mode and re-enables the GPU on its way out)."""
    hwnd = user32.find_window(MESSAGE_WINDOW_TITLE)
    return bool(hwnd) and user32.post_message(hwnd, user32.WM_APP_QUIT)
