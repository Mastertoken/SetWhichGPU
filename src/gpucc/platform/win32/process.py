"""Process information: image path, version resources, parent map. Read-only."""

from __future__ import annotations

import ctypes
from ctypes import wintypes as wt

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TH32CS_SNAPPROCESS = 0x2
_INVALID_HANDLE_VALUE = wt.HANDLE(-1).value

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]

_ver = ctypes.WinDLL("version")
_ver.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.DWORD)]
_ver.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
_ver.VerQueryValueW.argtypes = [ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT)]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", wt.LONG),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.WCHAR * 260),
    )


_k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]


def image_path(pid: int) -> tuple[str | None, int]:
    """(full image path or None, last Win32 error)."""
    h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None, ctypes.get_last_error()
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wt.DWORD(len(buf))
        if _k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value, 0
        return None, ctypes.get_last_error()
    finally:
        _k32.CloseHandle(h)


_EPOCH_AS_FILETIME = 116444736000000000
_k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4


def creation_time(pid: int) -> float | None:
    """Process start as epoch seconds (GetProcessTimes)."""
    h = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        created, exited, kernel, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not _k32.GetProcessTimes(h, *(ctypes.byref(t) for t in (created, exited, kernel, user))):
            return None
        ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        return (ticks - _EPOCH_AS_FILETIME) / 1e7
    finally:
        _k32.CloseHandle(h)


def parent_map() -> dict[int, int]:
    """pid → parent pid for all processes (Toolhelp snapshot)."""
    snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE_VALUE:
        return {}
    out: dict[int, int] = {}
    try:
        entry = _PROCESSENTRY32W(dwSize=ctypes.sizeof(_PROCESSENTRY32W))
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return out


def process_names() -> set[str]:
    """Lower-case executable names of all running processes (Toolhelp snapshot)."""
    snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if not snap or snap == _INVALID_HANDLE_VALUE:
        return set()
    names: set[str] = set()
    try:
        entry = _PROCESSENTRY32W(dwSize=ctypes.sizeof(_PROCESSENTRY32W))
        ok = _k32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            names.add(str(entry.szExeFile).lower())
            ok = _k32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _k32.CloseHandle(snap)
    return names


def version_strings(path: str) -> dict[str, str]:
    """ProductName / FileDescription / CompanyName from the file's version resource."""
    size = int(_ver.GetFileVersionInfoSizeW(path, None))
    if not size:
        return {}
    data = ctypes.create_string_buffer(size)
    if not _ver.GetFileVersionInfoW(path, 0, size, data):
        return {}
    ptr, length = ctypes.c_void_p(), wt.UINT()
    langs: list[tuple[int, int]] = []
    if _ver.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) and ptr.value:
        arr = ctypes.cast(ptr, ctypes.POINTER(wt.WORD))
        langs = [(int(arr[i]), int(arr[i + 1])) for i in range(0, length.value // 2, 2)]
    langs += [(0x0409, 0x04B0), (0x0409, 0x04E4), (0x0000, 0x04B0)]
    out: dict[str, str] = {}
    for field in ("ProductName", "FileDescription", "CompanyName"):
        for lang, cp in langs:
            q = f"\\StringFileInfo\\{lang:04X}{cp:04X}\\{field}"
            if _ver.VerQueryValueW(data, q, ctypes.byref(ptr), ctypes.byref(length)) and ptr.value and length.value:
                value = ctypes.wstring_at(ptr.value, length.value).rstrip("\x00").strip()
                if value:
                    out[field] = value
                    break
    return out
