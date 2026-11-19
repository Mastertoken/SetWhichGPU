"""Builds the overlay's display state from domain data (pure → unit-testable without Qt).

Rule: the stored preference and the observed GPU are always shown as two separate lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

from gpucc.assignment.support import support_for
from gpucc.core.models import (
    Confidence,
    DiscoveryResult,
    GpuKey,
    GpuSnapshot,
    ObservedGpu,
    PreferenceKind,
    PreferredGpu,
    TargetApp,
)
from gpucc.i18n import decimal_separator, tr
from gpucc.localai.runtimes import RUNTIMES, ModelReport


class Level(StrEnum):
    OK = "ok"
    WARN = "warn"
    MUTED = "muted"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class GpuRow:
    key: GpuKey
    name: str
    badge: str  # "iGPU" / ""
    util_pct: float | None
    util_text: str
    vram_text: str
    temp_text: str
    power_text: str
    used_by_target: bool
    preferred: bool
    assignable: bool = False


@dataclass(frozen=True, slots=True)
class ProcessRow:
    gpu_name: str
    activity_text: str
    vram_text: str


@dataclass(frozen=True, slots=True)
class OverlayState:
    has_target: bool
    title: str
    subtitle: str
    details: str
    observed_text: str
    observed_level: Level
    preferred_text: str
    preferred_level: Level
    status_text: str
    status_level: Level
    gpus: tuple[GpuRow, ...]
    processes: tuple[ProcessRow, ...]
    notes: tuple[str, ...]
    hotkey_text: str
    can_assign: bool = False
    assign_reason: str = ""
    current_choice: GpuKey | None = None  # None = Windows default
    default_label: str = ""
    gamemode_gpu: GpuKey | None = None  # offer: disable this GPU while the game runs (ADR-0002)
    gamemode_label: str = ""
    ai_title: str = ""  # "Loaded models (Ollama)" – empty: section hidden (ADR-0003)
    ai_lines: tuple[str, ...] = ()


GIB = 1 << 30


def kind_label(kind: PreferenceKind) -> str:
    return {
        PreferenceKind.DEFAULT: tr("Windows default"),
        PreferenceKind.POWER_SAVING: tr("Power saving"),
        PreferenceKind.HIGH_PERFORMANCE: tr("High performance"),
        PreferenceKind.SPECIFIC: tr("specific GPU"),
    }.get(kind, "")


def de(value: float, digits: int = 1) -> str:
    """Locale-aware decimal formatting: 9.84 → '9,8' (de) / '9.8' (en)."""
    return f"{value:.{digits}f}".replace(".", decimal_separator())


def fmt_gib(value: int) -> str:
    gib = value / GIB
    return de(gib, 0) if gib >= 100 else de(gib, 1)


def fmt_vram(used: int | None, total: int, integrated: bool) -> str:
    if integrated:
        # PDH "dedicated" for an iGPU is only the small carve-out; real usage is in shared RAM.
        return tr("{size} reserved · shared memory", size=fmt_bytes_short(used)) if used else tr("shared memory")
    if used is None:
        return f"– / {fmt_gib(total)} GB"
    return f"{fmt_gib(used)} / {fmt_gib(total)} GB"


def fmt_bytes_short(value: int) -> str:
    mib = value / (1 << 20)
    return f"{de(value / GIB)} GB" if mib >= 1024 else f"{mib:.0f} MB"


def fmt_engines(engines: Mapping[str, float], threshold: float = 0.5) -> str:
    """{'3D': 41.2, 'Copy': 0.1} → '3D 41 %' (busiest first, idle engines hidden)."""
    busy = sorted(((e, v) for e, v in engines.items() if v >= threshold), key=lambda kv: -kv[1])
    return ", ".join(f"{e} {v:.0f} %" for e, v in busy) or tr("no load")


def _name(discovery: DiscoveryResult, key: GpuKey | None) -> str:
    g = discovery.by_key(key) if key else None
    return g.short_name if g else tr("unknown")


def build_state(
    *,
    target: TargetApp | None,
    discovery: DiscoveryResult,
    snapshot: GpuSnapshot | None,
    observed: ObservedGpu | None,
    preferred: PreferredGpu | None,
    hotkey_text: str,
    target_running: bool = True,
    last_change_at: float | None = None,
    gamemode_note: str | None = None,
    ai_runtime: str | None = None,
    ai_enabled: bool = False,
    ai_report: ModelReport | None = None,
) -> OverlayState:
    notes: list[str] = []
    observed_key = observed.key if observed and observed.confidence is not Confidence.NONE else None
    preferred_key = preferred.key if preferred else None

    # --- GPU rows
    rows: list[GpuRow] = []
    for g in discovery.gpus:
        t = snapshot.for_gpu(g.key) if snapshot else None
        util = t.utilization_pct if t else None
        rows.append(
            GpuRow(
                key=g.key,
                name=g.short_name,
                badge="iGPU" if g.is_integrated else "",
                util_pct=util,
                util_text=f"{util:.0f} %" if util is not None else "–",
                vram_text=fmt_vram(t.vram_used_bytes if t else None, g.dedicated_vram_bytes, g.is_integrated),
                temp_text=f"{t.temperature_c:.0f} °C" if t and t.temperature_c is not None else "",
                power_text=f"{t.power_w:.0f} W" if t and t.power_w is not None else "",
                used_by_target=target is not None and g.key == observed_key,
                preferred=target is not None and g.key == preferred_key,
            )
        )

    if target is None:
        return OverlayState(
            has_target=False,
            title=tr("GPU overview"),
            subtitle=tr("No application in the foreground"),
            details="",
            observed_text="",
            observed_level=Level.MUTED,
            preferred_text="",
            preferred_level=Level.MUTED,
            status_text="",
            status_level=Level.MUTED,
            gpus=tuple(rows),
            processes=(),
            notes=(),
            hotkey_text=hotkey_text,
        )

    # --- observed
    if observed is None or observed.confidence is Confidence.NONE:
        observed_text, observed_level = tr("No GPU usage detected"), Level.MUTED
    else:
        name = _name(discovery, observed.key)
        top = observed.per_gpu[0] if observed.per_gpu else None
        if observed.confidence is Confidence.HIGH and top:
            observed_text = tr("{gpu} · active {pct} %", gpu=name, pct=f"{top.render_pct:.0f}")
        elif observed.confidence is Confidence.MEDIUM:
            observed_text = tr("{gpu} · memory in use, currently no load", gpu=name)
        else:
            observed_text = tr("{gpu} · several GPUs, largest memory share", gpu=name)
        observed_level = Level.OK if observed.confidence is Confidence.HIGH else Level.MUTED

    # --- preferred
    if preferred is None or preferred.kind is PreferenceKind.NONE:
        default = _name(discovery, discovery.default)
        preferred_text, preferred_level = tr("None – Windows decides ({gpu})", gpu=default), Level.MUTED
    elif preferred.kind is PreferenceKind.UNKNOWN:
        preferred_text, preferred_level = tr("Unknown entry: {raw}", raw=preferred.raw), Level.WARN
    elif preferred.stale:
        preferred_text = tr("GPU {token} not present – Windows uses its default", token=preferred.specific_token)
        preferred_level = Level.WARN
    else:
        preferred_text = f"{_name(discovery, preferred.key)} ({kind_label(preferred.kind)})"
        preferred_level = Level.OK

    # --- status (comparison of the two, never merged)
    status_text, status_level = status_for(
        app_name=target.display_name,
        preferred=preferred,
        observed=observed,
        started_at=target.started_at,
        last_change_at=last_change_at,
    )
    if not target.running:  # chosen from the side panel's "saved"/"installed" groups
        observed_text, observed_level = tr("– (not running)"), Level.MUTED
        if preferred is not None and preferred.is_own_preference and not preferred.stale:
            status_text, status_level = tr("Not running – the preference applies on next start"), Level.MUTED
        elif not (preferred is not None and preferred.stale):
            status_text, status_level = tr("Not running – no own GPU preference"), Level.MUTED

    # --- assignment options
    support = support_for(target, None, discovery)
    assignable = frozenset(r.key for r in rows if support.supported and support_for(target, r.key, discovery).supported)
    rows = [replace(r, assignable=r.key in assignable) for r in rows]
    default_name = _name(discovery, discovery.default)

    # --- processes of the target group
    procs = tuple(
        ProcessRow(
            gpu_name=_name(discovery, s.key),
            activity_text=fmt_engines(s.engines),
            vram_text=fmt_bytes_short(s.dedicated_bytes) if s.dedicated_bytes else "–",
        )
        for s in (observed.per_gpu if observed else ())
    )

    ai_title, ai_lines = "", tuple[str, ...]()
    if ai_runtime and target.running:
        if ai_enabled:
            ai_title = tr("LOADED AI MODELS ({runtime})", runtime=ai_runtime).upper()
            report = ai_report if ai_report is not None and ai_report.runtime == ai_runtime else None
            ai_lines = model_lines(report, observed, discovery)
        else:
            notes.append(
                tr("{runtime}: loaded models can be shown – tray menu → Show loaded AI models", runtime=ai_runtime)
            )

    offer = None if gamemode_note else gamemode_offer(target, preferred, observed, last_change_at, discovery)
    if gamemode_note:
        notes.append(gamemode_note)
    if target.exe_note:
        notes.append(target.exe_note)
    if target.exe_missing:
        notes.append(tr("Program file no longer exists (e.g. old version) – the entry can be reset."))
    elif target.running and not target_running:
        notes.append(tr("Application has exited – values show the last known state."))
    if target.access_denied:
        notes.append(tr("Protected process – path and details not readable."))
    if target.is_uwp:
        notes.append(tr("Store app detected (resolved via ApplicationFrameHost)."))
    if target.running and not target.hwnd:
        notes.append(tr("Background process without a window."))

    details = f"PID {target.pid}" if target.running else tr("not running")
    if target.company:
        details += f" · {target.company}"
    subtitle = target.exe_name
    if target.exe_path:
        subtitle += f" · {target.exe_path}"
    return OverlayState(
        has_target=True,
        title=target.display_name,
        subtitle=subtitle,
        details=details,
        observed_text=observed_text,
        observed_level=observed_level,
        preferred_text=preferred_text,
        preferred_level=preferred_level,
        status_text=status_text,
        status_level=status_level,
        gpus=tuple(rows),
        processes=procs,
        notes=tuple(notes),
        hotkey_text=hotkey_text,
        can_assign=support.supported,
        assign_reason=support.reason,
        current_choice=preferred.choice if preferred else None,
        default_label=tr("Windows default  (decides itself: {gpu})", gpu=default_name),
        gamemode_gpu=offer,
        gamemode_label=tr("🎮 Game mode: disable {gpu} while playing …", gpu=_name(discovery, offer)) if offer else "",
        ai_title=ai_title,
        ai_lines=ai_lines,
    )


def model_lines(
    report: ModelReport | None, observed: ObservedGpu | None, discovery: DiscoveryResult
) -> tuple[str, ...]:
    """Loaded models plus *measured* GPU placement. The runtimes don't say which GPU – we measure it."""
    if report is None:
        return (tr("Asking the runtime …"),)
    if not report.reachable:
        if report.problem == "unauthorized":
            return (tr("The local API requires an API token – not supported."),)
        if any(r.name == report.runtime and r.has_server_switch for r in RUNTIMES):
            return (
                tr(
                    "{runtime} API not reachable (port {port}) – start the local server in {runtime}.",
                    runtime=report.runtime,
                    port=report.port,
                ),
            )
        return (tr("{runtime} API not reachable (port {port}).", runtime=report.runtime, port=report.port),)
    if not report.models:
        return (tr("No model loaded"),)

    gpus = [s for s in (observed.per_gpu if observed else ()) if s.dedicated_bytes or s.render_pct]
    lines = []
    for m in report.models:
        parts = [f"{m.name} ×{m.instances}" if m.instances > 1 else m.name]
        if m.detail:
            parts.append(m.detail)
        if m.size_bytes:
            parts.append(fmt_bytes_short(m.size_bytes))
        if m.vram_bytes is not None and m.size_bytes:
            gpu_pct = round(100 * min(m.vram_bytes, m.size_bytes) / m.size_bytes)
            if gpu_pct == 0:
                parts.append(tr("CPU only"))
            elif gpu_pct < 100:
                parts.append(tr("{gpu} % GPU / {cpu} % CPU", gpu=gpu_pct, cpu=100 - gpu_pct))
        lines.append(" · ".join(parts))
    if len(gpus) == 1:
        lines.append(tr("Runs on {gpu} (measured)", gpu=_name(discovery, gpus[0].key)))
    elif len(gpus) > 1:
        split = ", ".join(f"{_name(discovery, s.key)} {fmt_bytes_short(s.dedicated_bytes)}" for s in gpus)
        lines.append(tr("Spread over several GPUs (measured): {split}", split=split))
    else:
        lines.append(tr("No GPU usage measured right now"))
    return tuple(lines)


def gamemode_offer(
    target: TargetApp,
    preferred: PreferredGpu | None,
    observed: ObservedGpu | None,
    last_change_at: float | None,
    discovery: DiscoveryResult,
) -> GpuKey | None:
    """The GPU to disable if – and only if – the app provably ignores its preference (ADR-0002)."""
    if not (target.running and target.exe_path and preferred and preferred.is_own_preference and not preferred.stale):
        return None
    if observed is None or observed.confidence not in (Confidence.HIGH, Confidence.MEDIUM) or observed.key is None:
        return None
    started_after_change = (
        target.started_at is not None and last_change_at is not None and target.started_at >= last_change_at
    )
    if not started_after_change or observed.key == preferred.key or observed.key in discovery.display_gpus:
        return None
    return observed.key


def status_for(
    *,
    app_name: str,
    preferred: PreferredGpu | None,
    observed: ObservedGpu | None,
    started_at: float | None,
    last_change_at: float | None,
) -> tuple[str, Level]:
    """Compare stored preference and measurement. 'Restart' only if the app predates our change."""
    has_pref = preferred is not None and preferred.is_own_preference and not preferred.stale
    confident = observed is not None and observed.confidence in (Confidence.HIGH, Confidence.MEDIUM)
    observed_key = observed.key if observed is not None and confident else None
    known_order = started_at is not None and last_change_at is not None
    restart_pending = (
        known_order and started_at is not None and last_change_at is not None and started_at < last_change_at
    )

    if preferred is not None and preferred.stale:
        return tr("Preference has no effect – preferred GPU is missing"), Level.WARN
    if has_pref and preferred is not None and confident:
        if observed_key == preferred.key:
            return tr("GPU preference active"), Level.OK
        if restart_pending:
            return tr("Saved – restart {app} to use the new GPU", app=app_name), Level.WARN
        if known_order:
            return tr(
                "{app} uses a different GPU despite the preference – the application apparently picks its GPU "
                "itself. Cannot be forced via Windows; only a GPU option inside the application helps.",
                app=app_name,
            ), Level.WARN
        return tr("Mismatch – restart needed or the application picks its GPU itself"), Level.WARN
    if has_pref:
        if restart_pending:
            return tr("Saved – takes effect after restarting {app}", app=app_name), Level.WARN
        return tr("Preference saved – usage currently not measurable"), Level.MUTED
    if restart_pending:
        return tr("Reset to Windows default – takes effect after restarting {app}", app=app_name), Level.WARN
    return tr("No own GPU preference"), Level.MUTED
