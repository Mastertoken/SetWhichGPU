"""Parsing of PDH GPU counter instance names (pure).

Examples::

    pid_1234_luid_0x00000000_0x0000FEF3_phys_0_eng_0_engtype_3D      (GPU Engine)
    pid_1234_luid_0x00000000_0x0000FEF3_phys_0                       (GPU Process Memory)
    luid_0x00000000_0x0000FEF3_phys_0                                (GPU Adapter Memory)
"""

from __future__ import annotations

import re

_LUID = r"luid_0x([0-9A-Fa-f]{8})_0x([0-9A-Fa-f]{8})"
_ENGINE_RE = re.compile(rf"^pid_(\d+)_{_LUID}_phys_\d+_eng_\d+_engtype_(.*)$")
_PROCESS_MEM_RE = re.compile(rf"^pid_(\d+)_{_LUID}_phys_\d+$")
_ADAPTER_MEM_RE = re.compile(rf"^{_LUID}_phys_\d+$")


def _luid(high: str, low: str) -> int:
    return (int(high, 16) << 32) | int(low, 16)


def parse_engine(name: str) -> tuple[int, int, str] | None:
    """→ (pid, luid, engine_type)"""
    m = _ENGINE_RE.match(name)
    return (int(m[1]), _luid(m[2], m[3]), m[4]) if m else None


def parse_process_memory(name: str) -> tuple[int, int] | None:
    """→ (pid, luid)"""
    m = _PROCESS_MEM_RE.match(name)
    return (int(m[1]), _luid(m[2], m[3])) if m else None


def parse_adapter_memory(name: str) -> int | None:
    """→ luid"""
    m = _ADAPTER_MEM_RE.match(name)
    return _luid(m[1], m[2]) if m else None
