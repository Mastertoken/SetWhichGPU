"""Window, monitor, hotkey and focus helpers (user32/shell32/kernel32)."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes as wt

WM_HOTKEY = 0x0312
WM_DISPLAYCHANGE = 0x007E
WM_DEVICECHANGE = 0x0219
WM_APP = 0x8000
WM_APP_SHOW_OVERLAY = WM_APP + 0x47

# SHQueryUserNotificationState
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4

ERROR_HOTKEY_ALREADY_REGISTERED = 1409
ERROR_ALREADY_EXISTS = 183

_u32 = ctypes.WinDLL("user32", use_last_error=True)
_s32 = ctypes.WinDLL("shell32")
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_u32.GetForegroundWindow.restype = wt.HWND
_u32.SetForegroundWindow.argtypes = [wt.HWND]
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_u32.GetWindowThreadProcessId.restype = wt.DWORD
_u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.MonitorFromWindow.restype = wt.HANDLE
_u32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
_u32.GetMonitorInfoW.argtypes = [wt.HANDLE, ctypes.c_void_p]
_u32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
_u32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
_u32.FindWindowW.restype = wt.HWND
_u32.FindWindowW.argtypes = [wt.LPCWSTR, wt.LPCWSTR]
_u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_u32.IsWindow.argtypes = [wt.HWND]
_EnumChildProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_u32.EnumChildWindows.argtypes = [wt.HWND, _EnumChildProc, wt.LPARAM]
_k32.CreateMutexW.restype = wt.HANDLE
_k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
        ("szDevice", wt.WCHAR * 32),
    )


def foreground_window() -> int:
    return int(_u32.GetForegroundWindow() or 0)


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def window_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    _u32.GetWindowTextW(hwnd, buf, len(buf))
    return buf.value


def window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def monitor_origin(hwnd: int) -> tuple[int, int] | None:
    """Physical top-left corner of the monitor showing ``hwnd`` (MONITOR_DEFAULTTONEAREST)."""
    mon = _u32.MonitorFromWindow(hwnd, 2)
    info = _MONITORINFOEXW(cbSize=ctypes.sizeof(_MONITORINFOEXW))
    if not mon or not _u32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    return int(info.rcMonitor.left), int(info.rcMonitor.top)


def notification_state() -> int:
    state = ctypes.c_int(0)
    if _s32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return 0
    return int(state.value)


def set_foreground(hwnd: int) -> bool:
    return bool(_u32.SetForegroundWindow(hwnd))


def is_window(hwnd: int) -> bool:
    return bool(_u32.IsWindow(hwnd))


def child_window_of_other_process(hwnd: int, owner_pid: int) -> int | None:
    """First child window belonging to a different process (UWP CoreWindow in ApplicationFrameHost)."""
    found: list[int] = []

    def _visit(child: int, _lparam: int) -> bool:
        if window_pid(child) != owner_pid:
            found.append(int(child))
            return False
        return True

    callback = _EnumChildProc(_visit)  # keep a reference for the duration of the call
    _u32.EnumChildWindows(hwnd, callback, 0)
    return found[0] if found else None


_GW_OWNER = 4
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14
_EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_u32.EnumWindows.argtypes = [_EnumWindowsProc, wt.LPARAM]
_u32.IsWindowVisible.argtypes = [wt.HWND]
_u32.GetWindow.restype = wt.HWND
_u32.GetWindow.argtypes = [wt.HWND, wt.UINT]
_u32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_u32.GetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int]
_dwm = ctypes.WinDLL("dwmapi")
_dwm.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]


def _is_cloaked(hwnd: int) -> bool:
    """UWP/virtual-desktop windows can be 'visible' but cloaked (not on screen)."""
    cloaked = wt.DWORD(0)
    if _dwm.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
        return False
    return bool(cloaked.value)


def app_windows() -> list[int]:
    """Top-level windows a user would call 'an application' (Alt+Tab-like filter)."""
    found: list[int] = []

    def _visit(hwnd: int, _lparam: int) -> bool:
        h = int(hwnd)
        if (
            _u32.IsWindowVisible(h)
            and not _u32.GetWindow(h, _GW_OWNER)
            and not (_u32.GetWindowLongPtrW(h, _GWL_EXSTYLE) & _WS_EX_TOOLWINDOW)
            and window_text(h)
            and not _is_cloaked(h)
        ):
            found.append(h)
        return True

    callback = _EnumWindowsProc(_visit)
    _u32.EnumWindows(callback, 0)
    return found


def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, vk: int) -> int:
    """0 on success, otherwise the Win32 error code."""
    if _u32.RegisterHotKey(hwnd, hotkey_id, modifiers, vk):
        return 0
    return ctypes.get_last_error() or -1


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    _u32.UnregisterHotKey(hwnd, hotkey_id)


def find_window(title: str) -> int:
    return int(_u32.FindWindowW(None, title) or 0)


def post_message(hwnd: int, msg: int, wparam: int = 0, lparam: int = 0) -> bool:
    return bool(_u32.PostMessageW(hwnd, msg, wparam, lparam))


EVENT_SYSTEM_FOREGROUND = 0x0003
_WINEVENT_OUTOFCONTEXT = 0x0000  # callback runs in *our* process via the message loop – no injection
_WINEVENT_SKIPOWNPROCESS = 0x0002
_WinEventProc = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, wt.LONG, wt.LONG, wt.DWORD, wt.DWORD)
_u32.SetWinEventHook.restype = wt.HANDLE
_u32.SetWinEventHook.argtypes = [wt.DWORD, wt.DWORD, wt.HMODULE, _WinEventProc, wt.DWORD, wt.DWORD, wt.DWORD]
_u32.UnhookWinEvent.argtypes = [wt.HANDLE]


class ForegroundHook:
    """Calls ``callback(hwnd)`` whenever another process's window becomes the foreground window.

    Must be installed on a thread with a message loop (the Qt GUI thread).
    """

    def __init__(self, callback: Callable[[int], None]) -> None:
        self._callback = callback
        self._proc = _WinEventProc(self._on_event)  # keep a reference while hooked
        self._hook = 0

    def _on_event(self, _hook: int, _event: int, hwnd: int, id_object: int, _child: int, _t: int, _ms: int) -> None:
        if hwnd and id_object == 0:  # OBJID_WINDOW
            self._callback(int(hwnd))

    @property
    def active(self) -> bool:
        return bool(self._hook)

    def start(self) -> bool:
        if not self._hook:
            self._hook = int(
                _u32.SetWinEventHook(
                    EVENT_SYSTEM_FOREGROUND,
                    EVENT_SYSTEM_FOREGROUND,
                    None,
                    self._proc,
                    0,
                    0,
                    _WINEVENT_OUTOFCONTEXT | _WINEVENT_SKIPOWNPROCESS,
                )
                or 0
            )
        return self.active

    def stop(self) -> None:
        if self._hook:
            _u32.UnhookWinEvent(self._hook)
            self._hook = 0


def ui_language_id() -> int | None:
    """LANGID of the user's Windows display language (GetUserDefaultUILanguage)."""
    try:
        return int(_k32.GetUserDefaultUILanguage())
    except OSError:
        return None


def acquire_singleton(name: str) -> tuple[int, bool]:
    """(mutex handle, already_running). Keep the handle alive for the process lifetime."""
    h = _k32.CreateMutexW(None, False, name)
    return int(h or 0), ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def release_singleton(handle: int) -> None:
    """Close our handle; the named mutex disappears once no process holds one."""
    if handle:
        _k32.CloseHandle(ctypes.c_void_p(handle))
