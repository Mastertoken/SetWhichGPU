from gpucc.app import migrate_autostart
from gpucc.diagnostics.paths import migrate_legacy_dir


def test_legacy_data_dir_is_moved_once(tmp_path):
    legacy = tmp_path / "GpuControlCenter"
    (legacy / "logs").mkdir(parents=True)
    (legacy / "gpucc.db").write_text("journal")
    new = tmp_path / "SetWhichGPU"
    assert migrate_legacy_dir(new, legacy)
    assert (new / "gpucc.db").read_text() == "journal" and (new / "logs").is_dir()
    assert not legacy.exists()
    assert not migrate_legacy_dir(new, legacy)  # nothing left to do


def test_existing_new_dir_is_never_overwritten(tmp_path):
    legacy, new = tmp_path / "old", tmp_path / "new"
    legacy.mkdir()
    (legacy / "gpucc.db").write_text("old")
    new.mkdir()
    (new / "gpucc.db").write_text("new")
    assert not migrate_legacy_dir(new, legacy)
    assert (new / "gpucc.db").read_text() == "new"


class FakeAutostart:
    def __init__(self, cmd=None):
        self.cmd = cmd

    def command(self):
        return self.cmd

    def enable(self, cmd):
        self.cmd = cmd

    def disable(self):
        self.cmd = None


def test_autostart_migration_only_carries_over_enabled_state():
    current, legacy = FakeAutostart(), FakeAutostart('"old.exe" -m gpucc')
    assert migrate_autostart(current, legacy, '"new.exe" -m gpucc')
    assert current.cmd == '"new.exe" -m gpucc' and legacy.cmd is None
    off, legacy_off = FakeAutostart(), FakeAutostart()
    assert not migrate_autostart(off, legacy_off, "x")
    assert off.cmd is None  # never enables autostart on its own


def test_icon_assets_present():
    from gpucc.ui.icons import ASSETS, ICON_SIZES

    assert all((ASSETS / f"icon-{s}.png").is_file() for s in ICON_SIZES)
