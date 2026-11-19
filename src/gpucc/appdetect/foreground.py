"""Application detection: foreground window, any app window, background GPU processes, saved exes."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from gpucc.core.models import FullscreenState, TargetApp
from gpucc.monitoring.attribution import process_tree
from gpucc.platform.win32 import process, user32

log = logging.getLogger(__name__)

#: Window classes of the shell – no "application" to target.
SHELL_CLASSES = frozenset({"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"})
UWP_FRAME_HOST = "applicationframehost.exe"
ERROR_ACCESS_DENIED = 5
#: Windowless processes from these folders are system components, not "applications".
SYSTEM_DIRS = (os.path.expandvars(r"%WINDIR%").lower() + "\\",)


def fullscreen_from_quns(state: int) -> FullscreenState:
    return {
        user32.QUNS_BUSY: FullscreenState.BORDERLESS,
        user32.QUNS_RUNNING_D3D_FULL_SCREEN: FullscreenState.EXCLUSIVE,
        user32.QUNS_PRESENTATION_MODE: FullscreenState.PRESENTATION,
    }.get(state, FullscreenState.NONE)


class WindowsForegroundProbe:
    def __init__(self, own_pid: int) -> None:
        self._own_pid = own_pid
        self._version_cache: dict[str, dict[str, str]] = {}

    def prewarm(self, paths: Iterable[str]) -> None:
        """Read version info ahead of time – called on the library worker thread so that the first
        application list does not stall the UI (e.g. while a sleeping hard disk spins up).
        Single dict assignments are atomic in CPython; a race only means a value is read twice."""
        for path in paths:
            if path:
                self._version(path)

    def _version(self, path: str | None) -> dict[str, str]:
        if not path:
            return {}
        key = path.lower()
        if key not in self._version_cache:
            self._version_cache[key] = process.version_strings(path) if os.path.exists(path) else {}
        return self._version_cache[key]

    # ------------------------------------------------------------------ windows
    def capture(self) -> TargetApp | None:
        hwnd = user32.foreground_window()
        target = self.capture_window(hwnd, with_state=True) if hwnd else None
        if target is not None:
            log.info(
                "target captured",
                extra={
                    "fields": {
                        "pid": target.pid,
                        "exe": target.exe_path,
                        "class": target.window_class,
                        "fullscreen": target.fullscreen.value,
                        "access_denied": target.access_denied,
                    }
                },
            )
        return target

    def capture_window(self, hwnd: int, with_state: bool = False) -> TargetApp | None:
        """Describe the application owning ``hwnd``; None for shell windows and ourselves."""
        if not hwnd or not user32.is_window(hwnd):
            return None
        cls = user32.window_class(hwnd)
        pid = user32.window_pid(hwnd)
        if cls in SHELL_CLASSES or pid == self._own_pid:
            return None
        path, err = process.image_path(pid)
        is_uwp = False
        if path and path.lower().endswith(UWP_FRAME_HOST):
            child = user32.child_window_of_other_process(hwnd, pid)
            if not child:
                return None  # suspended Store app: only the frame is left, no real application
            pid = user32.window_pid(child)
            path, err = process.image_path(pid)
            is_uwp = True
        info = self._version(path)
        return TargetApp(
            hwnd=hwnd,
            pid=pid,
            exe_path=path,
            title=user32.window_text(hwnd),
            window_class=cls,
            product_name=info.get("ProductName"),
            file_description=info.get("FileDescription"),
            company=info.get("CompanyName"),
            monitor_origin=user32.monitor_origin(hwnd),
            fullscreen=fullscreen_from_quns(user32.notification_state()) if with_state else FullscreenState.NONE,
            access_denied=path is None and err == ERROR_ACCESS_DENIED,
            is_uwp=is_uwp,
            started_at=process.creation_time(pid),
        )

    def running_apps(self) -> list[TargetApp]:
        """One entry per application with a visible top-level window (first window wins)."""
        out: dict[str, TargetApp] = {}
        for hwnd in user32.app_windows():
            t = self.capture_window(hwnd)
            if t is None:
                continue
            key = (t.exe_path or f"pid:{t.pid}").lower()
            out.setdefault(key, t)
        return list(out.values())

    # ------------------------------------------------------------------ windowless / not running
    def describe_process(self, pid: int) -> TargetApp | None:
        """A windowless process (e.g. a CUDA script); None for system components and ourselves."""
        if pid in (0, self._own_pid):
            return None
        path, err = process.image_path(pid)
        if path is None or path.lower().startswith(SYSTEM_DIRS):
            return None
        info = self._version(path)
        return TargetApp(
            hwnd=0,
            pid=pid,
            exe_path=path,
            title="",
            window_class="",
            product_name=info.get("ProductName"),
            file_description=info.get("FileDescription"),
            company=info.get("CompanyName"),
            access_denied=err == ERROR_ACCESS_DENIED,
            started_at=process.creation_time(pid),
        )

    def describe_exe(self, exe_path: str) -> TargetApp:
        """An application that is not running (pid 0) – e.g. from a saved preference."""
        info = self._version(exe_path)
        return TargetApp(
            hwnd=0,
            pid=0,
            exe_path=exe_path,
            title="",
            window_class="",
            product_name=info.get("ProductName"),
            file_description=info.get("FileDescription"),
            company=info.get("CompanyName"),
            exe_missing=not os.path.exists(exe_path),
        )

    def background_apps(self, pids: Iterable[int], exclude: Iterable[int] = ()) -> list[TargetApp]:
        skip = set(exclude)
        out = []
        for pid in pids:
            if pid in skip:
                continue
            t = self.describe_process(pid)
            if t is not None:
                out.append(t)
        return out

    def process_tree(self, pid: int) -> frozenset[int]:
        if pid == 0:
            return frozenset()
        return process_tree(pid, process.parent_map())

    def parent_map(self) -> dict[int, int]:
        return process.parent_map()
