"""How SetWhichGPU starts itself: from source (``pythonw -m gpucc``) or as the installed ``SetWhichGPU.exe``.

Every self-start goes through here – autostart, restart after a language change, the elevated game-mode
helper and the uninstaller's clean-up – so the frozen build and the source checkout behave the same.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

#: Sub-commands of the single executable (see ``gpucc.__main__``).
GAMEMODE_HELPER = "--gamemode-helper"
UNINSTALL = "--uninstall"


def frozen() -> bool:
    """True inside the PyInstaller build."""
    return bool(getattr(sys, "frozen", False))


def _gui_python() -> Path:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else exe


def self_command(*args: str) -> list[str]:
    """argv that starts SetWhichGPU (windowless) with ``args``."""
    if frozen():
        return [sys.executable, *args]
    return [str(_gui_python()), "-m", "gpucc", *args]


def self_command_line(*args: str) -> str:
    """Same as :func:`self_command`, quoted for the registry Run key (executable always in quotes)."""
    exe, *rest = self_command(*args)
    return f'"{exe}" {subprocess.list2cmdline(rest)}'.rstrip()


def split_for_shell_execute(argv: list[str]) -> tuple[str, str]:
    """(executable, parameters) as ShellExecuteEx expects them."""
    return argv[0], subprocess.list2cmdline(argv[1:])
