"""Resolve .lnk shortcut targets via the Shell's IShellLinkW (COM, read-only)."""

from __future__ import annotations

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes as wt

from gpucc.platform.win32._com import GUID, HRESULT, hr_failed, release, vcall

CLSID_ShellLink = GUID.parse("00021401-0000-0000-C000-000000000046")
IID_IShellLinkW = GUID.parse("000214F9-0000-0000-C000-000000000046")
IID_IPersistFile = GUID.parse("0000010b-0000-0000-C000-000000000046")
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2
_STGM_READ = 0x0
_MAX_PATH = 1024

_IUNKNOWN_QI = 0
_ISHELLLINK_GETPATH = 3
_IPERSISTFILE_LOAD = 5

_ole32 = ctypes.WinDLL("ole32")
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wt.DWORD]
_ole32.CoInitializeEx.restype = HRESULT
_ole32.CoUninitialize.argtypes = []
_ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
]  # fmt: skip
_ole32.CoCreateInstance.restype = HRESULT


@contextmanager
def com_apartment() -> Iterator[None]:
    """COM initialisation for the *current* thread (library scans run on a worker thread)."""
    hr = int(_ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED))
    try:
        yield
    finally:
        if hr >= 0:  # S_OK or S_FALSE (already initialised) must be balanced
            _ole32.CoUninitialize()


def resolve_shortcut(lnk_path: str) -> str | None:
    """Target path of a .lnk file, or None (URL/advertised shortcuts, errors). Needs com_apartment()."""
    link = ctypes.c_void_p()
    if hr_failed(
        int(
            _ole32.CoCreateInstance(
                ctypes.byref(CLSID_ShellLink), None, _CLSCTX_INPROC_SERVER, ctypes.byref(IID_IShellLinkW),
                ctypes.byref(link),
            )
        )
    ):  # fmt: skip
        return None
    persist = ctypes.c_void_p()
    try:
        hr = int(
            vcall(link, _IUNKNOWN_QI, HRESULT, [ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
                  ctypes.byref(IID_IPersistFile), ctypes.byref(persist))
        )  # fmt: skip
        if hr_failed(hr):
            return None
        if hr_failed(int(vcall(persist, _IPERSISTFILE_LOAD, HRESULT, [wt.LPCWSTR, wt.DWORD], lnk_path, _STGM_READ))):
            return None
        buf = ctypes.create_unicode_buffer(_MAX_PATH)
        hr = int(
            vcall(link, _ISHELLLINK_GETPATH, HRESULT, [wt.LPWSTR, ctypes.c_int, ctypes.c_void_p, wt.DWORD],
                  buf, _MAX_PATH, None, 0)
        )  # fmt: skip
        if hr_failed(hr) or not buf.value:
            return None
        return buf.value
    finally:
        release(persist)
        release(link)
