"""Device state (CfgMgr32, read-only) and pnputil enable/disable (game mode, ADR-0002).

pnputil is called WITHOUT /force and never with /remove-device. Disabling requires elevation;
reading the state does not.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes as wt

CM_PROB_DISABLED = 22
_CR_SUCCESS = 0
_CM_LOCATE_DEVNODE_NORMAL = 0
_DN_HAS_PROBLEM = 0x00000400
#: pnputil exit codes
PNPUTIL_OK = 0
PNPUTIL_REBOOT_REQUIRED = 3010

_cfg = ctypes.WinDLL("cfgmgr32")
_cfg.CM_Locate_DevNodeW.argtypes = [ctypes.POINTER(wt.DWORD), wt.LPCWSTR, wt.ULONG]
_cfg.CM_Locate_DevNodeW.restype = wt.DWORD
_cfg.CM_Get_DevNode_Status.argtypes = [ctypes.POINTER(wt.ULONG), ctypes.POINTER(wt.ULONG), wt.DWORD, wt.ULONG]
_cfg.CM_Get_DevNode_Status.restype = wt.DWORD


def device_problem(instance_id: str) -> int | None:
    """CM problem code of the device (0 = working), or None if the device is not present."""
    devinst = wt.DWORD()
    if _cfg.CM_Locate_DevNodeW(ctypes.byref(devinst), instance_id, _CM_LOCATE_DEVNODE_NORMAL) != _CR_SUCCESS:
        return None
    status, problem = wt.ULONG(), wt.ULONG()
    if _cfg.CM_Get_DevNode_Status(ctypes.byref(status), ctypes.byref(problem), devinst.value, 0) != _CR_SUCCESS:
        return None
    return int(problem.value) if status.value & _DN_HAS_PROBLEM else 0


def is_disabled(instance_id: str) -> bool:
    return device_problem(instance_id) == CM_PROB_DISABLED


def _pnputil() -> str:
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "pnputil.exe")


def pnputil(action: str, instance_id: str) -> int:
    """Run 'pnputil /disable-device|/enable-device <id>' (needs elevation). Returns the exit code."""
    if action not in ("/disable-device", "/enable-device"):
        raise ValueError(f"pnputil action not allowed: {action}")
    result = subprocess.run(
        [_pnputil(), action, instance_id],
        capture_output=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    return int(result.returncode)
