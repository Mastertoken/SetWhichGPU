"""Membership in the built-in group "Performance Log Users" (S-1-5-32-559), needed for ETW frame capture.

Windows only lets administrators and members of this group start the event-tracing sessions PresentMon uses.
SetWhichGPU asks ONCE (ADR-0004): an elevated helper adds the current user to the group. The group is
addressed by its well-known SID, never by its (localised) name; the user is passed as SID and validated.
The new membership is part of the user's token only after the next Windows sign-in.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import re
from ctypes import wintypes as wt
from enum import StrEnum

log = logging.getLogger(__name__)

PERF_LOG_USERS_SID = "S-1-5-32-559"
GRANT_PERFLOG = "--grant-perflog"  # sub-command of the executable (elevated helper)
_USER_SID = re.compile(r"S-1-5-21(-\d{1,10}){4}")  # local or domain/Microsoft account, never a built-in
ERROR_MEMBER_IN_ALIAS = 1378  # already a member → fine
EXIT_OK, EXIT_BAD_ARGS, EXIT_FAILED = 0, 2, 3

_advapi = ctypes.WinDLL("advapi32", use_last_error=True)
_netapi = ctypes.WinDLL("netapi32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_advapi.ConvertStringSidToSidW.argtypes = [wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
_advapi.ConvertStringSidToSidW.restype = wt.BOOL
_advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.LPWSTR)]
_advapi.ConvertSidToStringSidW.restype = wt.BOOL
_advapi.CheckTokenMembership.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(wt.BOOL)]
_advapi.CheckTokenMembership.restype = wt.BOOL
_advapi.LookupAccountSidW.argtypes = [
    wt.LPCWSTR,
    ctypes.c_void_p,
    wt.LPWSTR,
    ctypes.POINTER(wt.DWORD),
    wt.LPWSTR,
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(ctypes.c_int),
]
_advapi.LookupAccountSidW.restype = wt.BOOL
_advapi.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ctypes.POINTER(wt.HANDLE)]
_advapi.OpenProcessToken.restype = wt.BOOL
_advapi.GetTokenInformation.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD)]
_advapi.GetTokenInformation.restype = wt.BOOL
_k32.LocalFree.argtypes = [ctypes.c_void_p]
_k32.GetCurrentProcess.restype = wt.HANDLE
_k32.CloseHandle.argtypes = [wt.HANDLE]
_netapi.NetLocalGroupAddMembers.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_void_p, wt.DWORD]
_netapi.NetLocalGroupAddMembers.restype = wt.DWORD
_netapi.NetUserGetLocalGroups.argtypes = [
    wt.LPCWSTR,
    wt.LPCWSTR,
    wt.DWORD,
    wt.DWORD,
    ctypes.POINTER(ctypes.c_void_p),
    wt.DWORD,
    ctypes.POINTER(wt.DWORD),
    ctypes.POINTER(wt.DWORD),
]
_netapi.NetUserGetLocalGroups.restype = wt.DWORD
_netapi.NetApiBufferFree.argtypes = [ctypes.c_void_p]

_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_LG_INCLUDE_INDIRECT = 0x0001
_MAX_PREFERRED_LENGTH = 0xFFFFFFFF


class Access(StrEnum):
    READY = "ready"  # frame capture works now (member in the current token, or elevated)
    AFTER_SIGN_IN = "after_sign_in"  # member, but only from the next Windows sign-in on
    MISSING = "missing"  # not a member


def _sid(text: str) -> ctypes.c_void_p:
    sid = ctypes.c_void_p()
    if not _advapi.ConvertStringSidToSidW(text, ctypes.byref(sid)):
        raise OSError(ctypes.get_last_error(), "invalid SID")
    return sid


def _account_name(sid_text: str) -> tuple[str, str]:
    """(domain, name) of a SID – e.g. ('BUILTIN', 'Leistungsprotokollbenutzer') on a German Windows."""
    sid = _sid(sid_text)
    try:
        name, domain = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
        n_len, d_len, use = wt.DWORD(256), wt.DWORD(256), ctypes.c_int()
        if not _advapi.LookupAccountSidW(None, sid, name, n_len, domain, d_len, ctypes.byref(use)):
            raise OSError(ctypes.get_last_error(), "LookupAccountSid failed")
        return domain.value, name.value
    finally:
        _k32.LocalFree(sid)


def current_user_sid() -> str:
    token = wt.HANDLE()
    if not _advapi.OpenProcessToken(_k32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken failed")
    try:
        size = wt.DWORD()
        _advapi.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not _advapi.GetTokenInformation(token, _TOKEN_USER, buf, size, ctypes.byref(size)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation failed")
        user_sid = ctypes.c_void_p.from_buffer(buf).value  # TOKEN_USER.User.Sid is the first field
        text = wt.LPWSTR()
        if not _advapi.ConvertSidToStringSidW(user_sid, ctypes.byref(text)):
            raise OSError(ctypes.get_last_error(), "ConvertSidToStringSid failed")
        try:
            return str(text.value)
        finally:
            _k32.LocalFree(text)
    finally:
        _k32.CloseHandle(token)


def _token_has(sid_text: str) -> bool:
    sid = _sid(sid_text)
    try:
        member = wt.BOOL()
        return bool(_advapi.CheckTokenMembership(None, sid, ctypes.byref(member)) and member.value)
    finally:
        _k32.LocalFree(sid)


def _configured_member(user_sid: str) -> bool:
    """Member according to the account database (takes effect at the next sign-in)."""
    domain, user = _account_name(user_sid)
    _, group = _account_name(PERF_LOG_USERS_SID)
    buf = ctypes.c_void_p()
    read, total = wt.DWORD(), wt.DWORD()
    err = _netapi.NetUserGetLocalGroups(
        None,
        f"{domain}\\{user}",
        0,
        _LG_INCLUDE_INDIRECT,
        ctypes.byref(buf),
        _MAX_PREFERRED_LENGTH,
        ctypes.byref(read),
        ctypes.byref(total),
    )
    if err != 0:
        return False
    try:
        if not read.value or not buf.value:
            return False
        names = (ctypes.c_wchar_p * read.value).from_address(buf.value)  # LOCALGROUP_USERS_INFO_0[]
        return any((n or "").lower() == group.lower() for n in names)
    finally:
        _netapi.NetApiBufferFree(buf)


def access() -> Access:
    try:
        if _token_has(PERF_LOG_USERS_SID) or _elevated():
            return Access.READY
        return Access.AFTER_SIGN_IN if _configured_member(current_user_sid()) else Access.MISSING
    except OSError:
        log.exception("perflog access check failed")
        return Access.MISSING


def _elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


# ----------------------------------------------------------------------------- elevated helper


class _LOCALGROUP_MEMBERS_INFO_0(ctypes.Structure):
    _fields_ = (("lgrmi0_sid", ctypes.c_void_p),)


def add_to_group(user_sid: str) -> int:
    """Runs elevated. Adds exactly ``user_sid`` to Performance Log Users; nothing else."""
    if not _USER_SID.fullmatch(user_sid):
        return EXIT_BAD_ARGS
    _, group = _account_name(PERF_LOG_USERS_SID)
    sid = _sid(user_sid)
    try:
        info = _LOCALGROUP_MEMBERS_INFO_0(sid.value)
        err = _netapi.NetLocalGroupAddMembers(None, group, 0, ctypes.byref(info), 1)
    finally:
        _k32.LocalFree(sid)
    if err in (0, ERROR_MEMBER_IN_ALIAS):
        log.info("added to Performance Log Users", extra={"fields": {"already": err != 0}})
        return EXIT_OK
    log.error("NetLocalGroupAddMembers failed", extra={"fields": {"error": err}})
    return EXIT_FAILED


def helper_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="SetWhichGPU " + GRANT_PERFLOG, add_help=False)
    parser.add_argument("--user-sid", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_BAD_ARGS
    try:
        return add_to_group(args.user_sid)
    except OSError:
        log.exception("grant failed")
        return EXIT_FAILED


def request_access() -> tuple[Access, str]:
    """One UAC prompt → (new access state, problem: '' | 'declined' | 'failed')."""
    from gpucc.launch import self_command, split_for_shell_execute
    from gpucc.platform.win32.elevate import ERROR_CANCELLED, run_elevated_wait

    exe, params = split_for_shell_execute(self_command(GRANT_PERFLOG, "--user-sid", current_user_sid()))
    code, err = run_elevated_wait(exe, params)
    if err == ERROR_CANCELLED:
        return access(), "declined"
    if code != EXIT_OK:
        log.warning("perflog grant did not succeed", extra={"fields": {"code": code, "error": err}})
        return access(), "failed"
    return access(), ""
