from gpucc.core.models import GpuSnapshot, ProcessGpuUsage, TargetApp
from gpucc.ui.overlay.applist import AppGroup, background_candidates, build_app_list

MIB = 1 << 20
NV = "SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;"
UNITY = r"C:\Program Files\Unity\Hub\Editor\6000.6.9f1\Editor\Unity.exe"
AOM = r"D:\SteamLibrary\steamapps\common\Age of Mythology Retold\AoMRT_s.exe"
BLENDER = r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
OLD_UNITY = r"C:\Program Files\Unity\Hub\Editor\2022.3.1f1\Editor\Unity.exe"


def app(pid, path, name, hwnd=1):
    return TargetApp(hwnd=hwnd, pid=pid, exe_path=path, title=name, window_class="", file_description=name)


def describe(path):
    return TargetApp(
        hwnd=0,
        pid=0,
        exe_path=path,
        title="",
        window_class="",
        file_description=path.rsplit("\\", 1)[-1],
        exe_missing="2022" in path,
    )


def test_groups_dedupe_sorting_and_subtitles(discovery, keys):
    snap = GpuSnapshot(
        0,
        (),
        (
            ProcessGpuUsage(10, keys["nvidia"], {"3D": 99.0}, 4 << 30),  # AoM renders on RTX
            ProcessGpuUsage(20, keys["intel"], {}, 1440 * MIB),  # Unity idle, resident on Arc
            ProcessGpuUsage(21, keys["intel"], {}, 700 * MIB),  # Unity worker (child of 20)
            ProcessGpuUsage(30, keys["nvidia"], {"Compute_0": 80.0}, 2 << 30),  # windowless CUDA script
        ),
    )
    rows, targets = build_app_list(
        running=[app(20, UNITY, "Unity Editor"), app(10, AOM, "Age of Mythology: Retold"), app(11, AOM, "dup")],
        background=[app(30, r"C:\ai\python.exe", "Python", hwnd=0)],
        saved_values={UNITY: "GpuPreference=2;", AOM: NV, BLENDER: NV, OLD_UNITY: "GpuPreference=2;"},
        profile_paths=[BLENDER.upper()],  # same app, different case → one row
        describe_exe=describe,
        discovery=discovery,
        history=[snap],
        parents={21: 20},
    )
    assert [(r.group, r.title) for r in rows] == [
        (AppGroup.RUNNING, "Age of Mythology: Retold"),  # active first
        (AppGroup.RUNNING, "Unity Editor"),
        (AppGroup.BACKGROUND, "Python"),
        (AppGroup.SAVED, "blender.exe"),  # alphabetical within the group
        (AppGroup.SAVED, "Unity.exe"),  # old Unity version, file missing
    ]
    by_title = {r.title: r for r in rows}
    assert by_title["Age of Mythology: Retold"].subtitle == "nutzt GeForce RTX 3060 99 % · bevorzugt GeForce RTX 3060"
    assert by_title["Unity Editor"].subtitle == "nutzt Arc Pro B65 · bevorzugt Arc Pro B65"
    assert by_title["blender.exe"].subtitle == "bevorzugt GeForce RTX 3060"
    assert by_title["Unity.exe"].subtitle.startswith("Programmdatei fehlt")
    assert targets[BLENDER.lower()].pid == 0 and not targets[BLENDER.lower()].running
    assert targets[AOM.lower()].pid == 10  # first window wins


def test_background_candidates_thresholds(keys):
    snap = GpuSnapshot(
        0,
        (),
        (
            ProcessGpuUsage(1, keys["intel"], {"3D": 0.2}, 50 * MIB),  # too small
            ProcessGpuUsage(2, keys["nvidia"], {"Compute_0": 5.0}, MIB),  # active
            ProcessGpuUsage(3, keys["intel"], {}, 300 * MIB),  # large VRAM
            ProcessGpuUsage(4, keys["intel"], {"Copy": 50.0}, MIB),  # copy engine is not rendering
        ),
    )
    assert background_candidates(snap) == [2, 3]
    assert background_candidates(None) == []
