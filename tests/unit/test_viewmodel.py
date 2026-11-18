from gpucc.assignment.win_pref import interpret
from gpucc.core.models import (
    Confidence,
    GpuSnapshot,
    GpuTelemetry,
    ObservedGpu,
    ProcessGpuSummary,
    TargetApp,
)
from gpucc.ui.overlay.viewmodel import Level, build_state, de, fmt_vram

GIB = 1 << 30
MIB = 1 << 20
UNITY = TargetApp(
    1,
    21780,
    r"C:\Program Files\Unity\Hub\Editor\6000.6.9f1\Editor\Unity.exe",
    "DemoProject - Unity 6.6 <DX12>",
    "UnityContainerWndClass",
    product_name="Unity",
    file_description="Unity Editor",
    company="Unity Technologies",
)


def snapshot(discovery):
    gpus = tuple(
        GpuTelemetry(
            g.key,
            41.0 if g.vendor.value == "intel" else 2.0,
            {},
            int(9.8 * GIB),
            g.dedicated_vram_bytes,
            63.0 if g.vendor.value == "intel" else None,
            88.0 if g.vendor.value == "intel" else None,
            ("pdh",),
        )
        for g in discovery.gpus
    )
    return GpuSnapshot(0, gpus, ())


def test_formatting():
    assert de(9.84) == "9,8"
    assert fmt_vram(int(9.8 * GIB), 32 * GIB, False) == "9,8 / 32,0 GB"
    assert fmt_vram(None, 12 * GIB, False) == "– / 12,0 GB"
    assert fmt_vram(None, 0, True) == "geteilter Speicher"
    assert fmt_vram(15 * MIB, 485 * MIB, True) == "15 MB reserviert · geteilter Speicher"


def test_unity_preference_active(discovery, keys):
    arc = keys["intel"]
    observed = ObservedGpu(arc, Confidence.HIGH, (ProcessGpuSummary(arc, 41.0, 2 * GIB, {"3D": 41.0}),))
    s = build_state(
        target=UNITY,
        discovery=discovery,
        snapshot=snapshot(discovery),
        observed=observed,
        preferred=interpret("GpuPreference=2;", discovery),
        hotkey_text="Strg+Alt+G",
    )
    assert s.title == "Unity Editor"
    assert s.subtitle.startswith("Unity.exe · C:\\Program Files")
    assert s.details == "PID 21780 · Unity Technologies"
    assert s.observed_text == "Arc Pro B65 · aktiv 41 %"
    assert s.preferred_text == "Arc Pro B65 (Hohe Leistung)"
    assert (s.status_text, s.status_level) == ("GPU-Präferenz aktiv", Level.OK)
    row = next(r for r in s.gpus if r.key == arc)
    assert row.used_by_target and row.preferred
    assert (row.util_text, row.temp_text, row.power_text) == ("41 %", "63 °C", "88 W")
    amd = next(r for r in s.gpus if r.key == keys["amd"])
    assert amd.badge == "iGPU" and not amd.used_by_target
    assert s.processes[0].activity_text == "3D 41 %"


def test_preference_and_observation_stay_separate_on_mismatch(discovery, keys):
    observed = ObservedGpu(keys["intel"], Confidence.MEDIUM, (ProcessGpuSummary(keys["intel"], 0, GIB, {}),))
    pref = interpret("SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;", discovery)
    s = build_state(target=UNITY, discovery=discovery, snapshot=None, observed=observed, preferred=pref, hotkey_text="")
    assert s.observed_text.startswith("Arc Pro B65")
    assert s.preferred_text == "GeForce RTX 3060 (bestimmte GPU)"
    assert s.status_level is Level.WARN and "Neustart" in s.status_text


def test_stale_and_no_usage(discovery):
    pref = interpret("SpecificAdapter=DEAD&BEEF&00000000;GpuPreference=1073741824;", discovery)
    s = build_state(
        target=UNITY,
        discovery=discovery,
        snapshot=None,
        observed=ObservedGpu(None, Confidence.NONE),
        preferred=pref,
        hotkey_text="",
    )
    assert s.observed_text == "Keine GPU-Nutzung erkennbar"
    assert s.preferred_level is Level.WARN and "nicht vorhanden" in s.preferred_text
    assert s.status_level is Level.WARN


def test_no_preference_shows_windows_choice(discovery):
    s = build_state(
        target=UNITY,
        discovery=discovery,
        snapshot=None,
        observed=None,
        preferred=interpret(None, discovery),
        hotkey_text="",
    )
    assert s.preferred_text == "Keine – Windows entscheidet (Arc Pro B65)"
    assert s.status_text == "Keine eigene GPU-Präferenz"


def test_overview_without_target(discovery):
    s = build_state(
        target=None,
        discovery=discovery,
        snapshot=snapshot(discovery),
        observed=None,
        preferred=None,
        hotkey_text="Strg+Alt+G",
    )
    assert not s.has_target and s.title == "GPU-Übersicht"
    assert len(s.gpus) == 3 and not any(r.used_by_target or r.preferred for r in s.gpus)


def test_target_exited_note(discovery):
    s = build_state(
        target=UNITY,
        discovery=discovery,
        snapshot=None,
        observed=None,
        preferred=None,
        hotkey_text="",
        target_running=False,
    )
    assert any("beendet" in n for n in s.notes)


def test_protected_process_note(discovery):
    t = TargetApp(1, 4, None, "Secure", "Cls", access_denied=True)
    s = build_state(target=t, discovery=discovery, snapshot=None, observed=None, preferred=None, hotkey_text="")
    assert any("geschützt" in n for n in s.notes)
