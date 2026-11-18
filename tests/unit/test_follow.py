from gpucc.app import should_follow
from gpucc.core.models import TargetApp


def app(pid: int) -> TargetApp:
    return TargetApp(hwnd=pid * 10, pid=pid, exe_path=rf"C:\x\app{pid}.exe", title="", window_class="")


def test_follows_other_process():
    assert should_follow(app(1), app(2))
    assert should_follow(None, app(2))


def test_keeps_target_for_same_process_or_no_app():
    assert not should_follow(app(1), app(1))  # e.g. second Blender window
    assert not should_follow(app(1), None)  # desktop, taskbar or our own overlay
    assert not should_follow(None, None)
