"""Real Win32/vendor API calls – read-only. Run with: uv run pytest -m windows"""

import contextlib
import os
import time

import pytest

pytestmark = pytest.mark.windows


@pytest.fixture(scope="module")
def scan():
    """Real discovery; tests that need a GPU skip on machines without one (e.g. CI runners)."""
    from gpucc.discovery.service import WindowsGpuDiscovery

    result = WindowsGpuDiscovery().scan()
    if not result.gpus:
        pytest.skip("no physical GPU on this machine")
    return result


def test_discovery_finds_physical_gpus(scan):
    assert len({g.key for g in scan.gpus}) == len(scan.gpus)
    assert all(g.luid for g in scan.gpus)


def test_discovery_runs_without_gpu_too():
    from gpucc.discovery.service import WindowsGpuDiscovery

    WindowsGpuDiscovery().scan()  # must not raise, even with only the Basic Render Driver


def test_pdh_source_samples(scan):
    from gpucc.monitoring.sources.pdh import PdhSource

    r = scan
    src = PdhSource()
    assert src.available
    src.bind(r.gpus)
    time.sleep(0.5)
    s = src.sample()
    src.close()
    assert set(s.readings) == {g.key for g in r.gpus}
    assert any(p.dedicated_bytes > 0 for p in s.processes)


def test_foreground_probe_and_process_tree():
    from gpucc.appdetect.foreground import WindowsForegroundProbe

    probe = WindowsForegroundProbe(own_pid=-1)
    probe.capture()  # must not raise, may be None (e.g. desktop focused)
    assert os.getpid() in probe.process_tree(os.getpid())


def test_preference_reader_missing_value():
    from gpucc.platform.win32.registry import UserGpuPreferenceReader

    assert UserGpuPreferenceReader().read(r"Z:\does\not\exist.exe") is None


def test_app_enumeration_and_saved_entries():
    from gpucc.appdetect.foreground import WindowsForegroundProbe
    from gpucc.platform.win32.registry import UserGpuPreferenceRegistry

    probe = WindowsForegroundProbe(own_pid=os.getpid())
    apps = probe.running_apps()
    assert len({a.app_key for a in apps}) == len(apps)  # one row per application
    assert all(a.hwnd and a.running for a in apps)
    missing = probe.describe_exe(r"Z:\gone\old.exe")
    assert missing.exe_missing and not missing.running
    assert isinstance(UserGpuPreferenceRegistry().entries(), dict)  # read-only


def test_resolve_real_shortcut(tmp_path):
    import subprocess

    from gpucc.platform.win32.shell_link import com_apartment, resolve_shortcut

    lnk = tmp_path / "explorer.lnk"
    target = os.path.expandvars(r"%WINDIR%\explorer.exe")
    script = f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');$s.TargetPath='{target}';$s.Save()"
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True)
    with com_apartment():
        assert resolve_shortcut(str(lnk)).lower() == target.lower()
        assert resolve_shortcut(str(tmp_path / "missing.lnk")) is None


def test_foreground_hook_install_and_remove(qtbot):
    from gpucc.platform.win32.user32 import ForegroundHook

    events: list[int] = []
    hook = ForegroundHook(events.append)
    assert hook.start()
    assert hook.start()  # idempotent
    hook.stop()
    assert not hook.active
    hook.stop()  # idempotent


TEST_KEY = r"Software\SetWhichGPUTest"


@pytest.fixture
def test_key():
    import winreg

    yield TEST_KEY
    for sub in (TEST_KEY + r"\Prefs", TEST_KEY + r"\Run", TEST_KEY):
        with contextlib.suppress(FileNotFoundError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)


def test_registry_write_read_delete_in_test_key(test_key):
    from gpucc.platform.win32.registry import UserGpuPreferenceRegistry

    reg = UserGpuPreferenceRegistry(test_key + r"\Prefs")
    exe = r"C:\Program Files\Test App\app.exe"
    assert reg.read(exe) is None
    reg.write(exe, "SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;")
    assert reg.read(exe).startswith("SpecificAdapter=10DE")
    reg.delete(exe)
    assert reg.read(exe) is None
    reg.delete(exe)  # idempotent


def test_autostart_entry_in_test_key(test_key):
    from gpucc.platform.win32.registry import AutostartEntry

    entry = AutostartEntry("SetWhichGPU Test", test_key + r"\Run")
    assert entry.command() is None
    entry.enable('"C:\\x\\pythonw.exe" -m gpucc')
    assert entry.command() == '"C:\\x\\pythonw.exe" -m gpucc'
    entry.disable()
    assert entry.command() is None


def test_process_creation_time():
    import time

    from gpucc.platform.win32.process import creation_time

    started = creation_time(os.getpid())
    assert started is not None and started <= time.time() and time.time() - started < 24 * 3600


def test_device_state_read_only():
    from gpucc.discovery.service import WindowsGpuDiscovery
    from gpucc.platform.win32.cfgmgr import device_problem, is_disabled

    for gpu in WindowsGpuDiscovery().scan().gpus:
        if gpu.instance_id:
            assert device_problem(gpu.instance_id) == 0 and not is_disabled(gpu.instance_id)
    assert device_problem("PCI\\VEN_0000&DEV_0000\\does-not-exist") is None


def test_pnputil_rejects_other_actions():
    from gpucc.platform.win32.cfgmgr import pnputil

    for action in ("/remove-device", "/delete-driver", "/disable-device /force"):
        with pytest.raises(ValueError):
            pnputil(action, "PCI\\VEN_10DE&DEV_2504\\x")


def test_version_strings_of_explorer():
    from gpucc.platform.win32.process import version_strings

    info = version_strings(os.path.expandvars(r"%WINDIR%\explorer.exe"))
    assert info.get("CompanyName", "").startswith("Microsoft")
