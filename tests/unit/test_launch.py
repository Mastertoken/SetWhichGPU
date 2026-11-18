"""Self-start commands for the source checkout and the installed (frozen) build."""

import sys

import pytest

from gpucc import launch


@pytest.fixture
def installed(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Users\x\AppData\Local\Programs\SetWhichGPU\SetWhichGPU.exe")


def test_source_checkout_uses_pythonw_module():
    argv = launch.self_command("--restart")
    assert argv[1:] == ["-m", "gpucc", "--restart"]
    assert launch.self_command_line().startswith('"') and launch.self_command_line().endswith(" -m gpucc")


def test_installed_build_starts_its_own_exe(installed):
    assert launch.frozen()
    assert launch.self_command("--restart") == [sys.executable, "--restart"]
    assert launch.self_command_line() == f'"{sys.executable}"'


def test_gamemode_helper_and_restart_use_the_installed_exe(installed, tmp_path):
    from gpucc.app import autostart_command, restart_command
    from gpucc.gamemode.service import Session, helper_command

    exe, params = helper_command(Session("PCI\\VEN_10DE&DEV_2504\\x", "RTX", "Game.exe", "Game"), tmp_path)
    assert exe == sys.executable and params.startswith("--gamemode-helper ")
    assert restart_command() == [sys.executable, "--restart"]
    assert autostart_command() == f'"{sys.executable}"'


def test_refresh_autostart_only_rewrites_an_enabled_entry_pointing_elsewhere():
    from gpucc.app import refresh_autostart

    class Entry:
        def __init__(self, value):
            self.value = value

        def command(self):
            return self.value

        def enable(self, cmd):
            self.value = cmd

    new = '"C:\\new\\SetWhichGPU.exe"'
    assert not refresh_autostart(Entry(None), new)  # disabled stays disabled
    assert not refresh_autostart(Entry(new), new)
    moved = Entry('"C:\\old\\pythonw.exe" -m gpucc')
    assert refresh_autostart(moved, new) and moved.value == new


def test_main_dispatches_sub_commands(monkeypatch):
    import gpucc.__main__ as entry

    calls = []
    monkeypatch.setattr("gpucc.gamemode.helper.main", lambda a: calls.append(("helper", a)) or 0)
    monkeypatch.setattr("gpucc.uninstall.main", lambda a: calls.append(("uninstall", a)) or 0)
    monkeypatch.setattr(entry, "run_app", lambda: calls.append(("app", [])) or 0)
    for argv in (["--gamemode-helper", "--x"], ["--uninstall", "--revert-preferences"], []):
        monkeypatch.setattr(sys, "argv", ["SetWhichGPU.exe", *argv])
        assert entry.main() == 0
    assert calls == [("helper", ["--x"]), ("uninstall", ["--revert-preferences"]), ("app", [])]


def test_wait_until_times_out_without_sleeping_forever():
    from gpucc.uninstall import wait_until

    slept = []
    assert wait_until(lambda: True, 0)
    assert not wait_until(lambda: False, 0, sleep=slept.append)
