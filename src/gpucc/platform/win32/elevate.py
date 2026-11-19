"""Start a process elevated via UAC (ShellExecuteExW, verb 'runas')."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

ERROR_CANCELLED = 1223  # user declined the UAC prompt
_SEE_MASK_NOCLOSEPROCESS = 0x00000040
_SW_HIDE = 0


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = (
        ("cbSize", wt.DWORD),
        ("fMask", wt.ULONG),
        ("hwnd", wt.HWND),
        ("lpVerb", wt.LPCWSTR),
        ("lpFile", wt.LPCWSTR),
        ("lpParameters", wt.LPCWSTR),
        ("lpDirectory", wt.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wt.HINSTANCE),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", wt.LPCWSTR),
        ("hkeyClass", wt.HKEY),
        ("dwHotKey", wt.DWORD),
        ("hIconOrMonitor", wt.HANDLE),
        ("hProcess", wt.HANDLE),
    )


_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
_shell32.ShellExecuteExW.restype = wt.BOOL
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.GetProcessId.argtypes = [wt.HANDLE]
_k32.GetProcessId.restype = wt.DWORD
_k32.CloseHandle.argtypes = [wt.HANDLE]


_k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
_k32.WaitForSingleObject.restype = wt.DWORD
_k32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_k32.GetExitCodeProcess.restype = wt.BOOL
_WAIT_OBJECT_0 = 0


def run_elevated_wait(executable: str, parameters: str, timeout_ms: int = 30_000) -> tuple[int | None, int]:
    """Run elevated and wait: (exit code or None on timeout/failure, error). error 1223 = UAC declined."""
    info = _SHELLEXECUTEINFOW(
        cbSize=ctypes.sizeof(_SHELLEXECUTEINFOW),
        fMask=_SEE_MASK_NOCLOSEPROCESS,
        lpVerb="runas",
        lpFile=executable,
        lpParameters=parameters,
        nShow=_SW_HIDE,
    )
    if not _shell32.ShellExecuteExW(ctypes.byref(info)):
        return None, ctypes.get_last_error()
    if not info.hProcess:
        return None, 0
    try:
        if _k32.WaitForSingleObject(info.hProcess, timeout_ms) != _WAIT_OBJECT_0:
            return None, 0
        code = wt.DWORD()
        if not _k32.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            return None, ctypes.get_last_error()
        return int(code.value), 0
    finally:
        _k32.CloseHandle(info.hProcess)


def run_elevated(executable: str, parameters: str) -> tuple[int, int]:
    """(pid, error). error 1223 = UAC declined; pid 0 on failure."""
    info = _SHELLEXECUTEINFOW(
        cbSize=ctypes.sizeof(_SHELLEXECUTEINFOW),
        fMask=_SEE_MASK_NOCLOSEPROCESS,
        lpVerb="runas",
        lpFile=executable,
        lpParameters=parameters,
        nShow=_SW_HIDE,
    )
    if not _shell32.ShellExecuteExW(ctypes.byref(info)):
        return 0, ctypes.get_last_error()
    pid = int(_k32.GetProcessId(info.hProcess)) if info.hProcess else 0
    if info.hProcess:
        _k32.CloseHandle(info.hProcess)
    return pid, 0
