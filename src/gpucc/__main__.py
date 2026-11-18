"""Entry point: ``python -m gpucc``."""

from __future__ import annotations

import logging
import os
import sys
import time

SINGLETON_NAME = "Local\\SetWhichGPU.Singleton"
RESTART_WAIT_S = 15.0


def main() -> int:
    from gpucc.branding import LANGUAGE_SETTING, RESTART_FLAG
    from gpucc.diagnostics.logging import configure_logging
    from gpucc.diagnostics.paths import log_dir
    from gpucc.i18n import resolve_language, set_language
    from gpucc.platform.win32 import user32
    from gpucc.ui.hotkey import notify_running_instance

    configure_logging(log_dir())
    log = logging.getLogger("gpucc")

    mutex, already_running = user32.acquire_singleton(SINGLETON_NAME)
    if already_running and RESTART_FLAG in sys.argv[1:]:
        # Started by the previous instance (e.g. language change): wait until it has exited.
        deadline = time.monotonic() + RESTART_WAIT_S
        while already_running and time.monotonic() < deadline:
            user32.release_singleton(mutex)  # our own handle would keep the mutex alive
            time.sleep(0.2)
            mutex, already_running = user32.acquire_singleton(SINGLETON_NAME)
    if already_running:
        log.info("already running – asking existing instance to show the overlay")
        notify_running_instance()
        return 0

    from PySide6.QtWidgets import QApplication

    from gpucc.app import Controller, autostart_command, configured_hotkey, migrate_autostart
    from gpucc.appdetect.foreground import WindowsForegroundProbe
    from gpucc.branding import APP_NAME, LEGACY_AUTOSTART_NAME
    from gpucc.diagnostics.paths import data_dir
    from gpucc.discovery.service import WindowsGpuDiscovery
    from gpucc.platform.win32.registry import AutostartEntry, UserGpuPreferenceRegistry
    from gpucc.profiles.store import ProfileStore
    from gpucc.ui.icons import app_icon

    store = ProfileStore(data_dir() / "gpucc.db")
    # Saved choice (tray → Language), else the Windows UI language; GPUCC_LANG=en|de overrides both.
    set_language(resolve_language(store.get_setting(LANGUAGE_SETTING), user32.ui_language_id()))

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    autostart = AutostartEntry()
    if migrate_autostart(autostart, AutostartEntry(LEGACY_AUTOSTART_NAME), autostart_command()):
        log.info("autostart entry migrated from the former product name")
    controller = Controller(
        app,
        discovery=WindowsGpuDiscovery(),
        probe=WindowsForegroundProbe(os.getpid()),
        preferences=UserGpuPreferenceRegistry(),
        hotkey=configured_hotkey(),
        store=store,
        autostart=autostart,
    )
    controller.start()
    rc = app.exec()
    log.info("exit", extra={"fields": {"rc": rc}})
    del mutex
    return int(rc)


if __name__ == "__main__":
    raise SystemExit(main())
