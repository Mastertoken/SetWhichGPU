"""The 'restart needed?' logic – answers: when does the overlay say 'Neustart'?"""

import pytest

from gpucc.assignment.win_pref import interpret
from gpucc.core.models import Confidence, ObservedGpu
from gpucc.ui.overlay.viewmodel import Level, status_for

NV = "SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;"
CHANGE_AT = 1000.0


@pytest.fixture
def status(discovery, keys):
    def run(raw, observed_vendor, started_at, last_change_at=CHANGE_AT, confidence=Confidence.HIGH):
        observed = ObservedGpu(keys[observed_vendor], confidence) if observed_vendor else None
        return status_for(
            app_name="Blender",
            preferred=interpret(raw, discovery),
            observed=observed,
            started_at=started_at,
            last_change_at=last_change_at,
        )

    return run


def test_active_when_running_on_preferred_gpu(status):
    assert status(NV, "nvidia", started_at=2000) == ("GPU-Präferenz aktiv", Level.OK)


def test_restart_needed_only_if_app_started_before_change(status):
    text, level = status(NV, "intel", started_at=500)
    assert "Neustart von Blender nötig" in text and level is Level.WARN


def test_app_started_after_change_but_ignores_preference(status):
    text, level = status(NV, "intel", started_at=1500)
    assert "wählt ihre GPU offenbar selbst" in text and level is Level.WARN
    assert "Neustart" not in text


def test_unknown_order_for_external_changes(status):
    text, _ = status(NV, "intel", started_at=1500, last_change_at=None)
    assert text.startswith("Abweichung")


def test_restart_pending_without_measurable_usage(status):
    text, level = status(NV, None, started_at=500)
    assert text == "Gespeichert – wirksam nach Neustart von Blender" and level is Level.WARN
    text, level = status(NV, None, started_at=1500)
    assert "nicht messbar" in text and level is Level.MUTED


def test_reset_to_default_pending(status):
    text, level = status(None, "nvidia", started_at=500)
    assert "zurückgesetzt" in text and level is Level.WARN
    assert status(None, "nvidia", started_at=1500) == ("Keine eigene GPU-Präferenz", Level.MUTED)


def test_unity_class_preference_counts_as_own(status):
    assert status("GpuPreference=2;", "intel", started_at=2000, last_change_at=None)[0] == "GPU-Präferenz aktiv"
