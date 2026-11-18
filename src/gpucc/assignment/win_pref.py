"""Interpretation of HKCU\\…\\DirectX\\UserGpuPreferences values (pure, read-only).

Format (see docs/spikes/S1_specific_gpu.md)::

    GpuPreference=0;                                     Windows decides
    GpuPreference=1;                                     power saving
    GpuPreference=2;                                     high performance
    SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;   specific GPU (undocumented)

Unknown extra fields (AutoHDREnable=…, SwapEffectUpgradeEnable=…) must be preserved by writers.
"""

from __future__ import annotations

from gpucc.core.models import DiscoveryResult, GpuKey, PreferenceKind, PreferredGpu

GPU_PREFERENCE_SPECIFIC = 1073741824  # 0x40000000

_CLASS_KINDS = {
    0: PreferenceKind.DEFAULT,
    1: PreferenceKind.POWER_SAVING,
    2: PreferenceKind.HIGH_PERFORMANCE,
    GPU_PREFERENCE_SPECIFIC: PreferenceKind.SPECIFIC,
}


def parse_fields(raw: str) -> dict[str, str]:
    """'A=1;B=x;' → {'A': '1', 'B': 'x'} (order preserved, keys case-sensitive as stored)."""
    out: dict[str, str] = {}
    for part in raw.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


_OWN_FIELDS = ("SpecificAdapter", "GpuPreference")


def serialize_fields(fields: dict[str, str]) -> str:
    return "".join(f"{k}={v};" for k, v in fields.items())


def compose(raw: str | None, choice: GpuKey | None) -> str | None:
    """New registry value for ``choice`` (a GPU, or None = Windows decides).

    Only ``SpecificAdapter``/``GpuPreference`` are touched; every other field (AutoHDREnable,
    SwapEffectUpgradeEnable …) is preserved in its original order. Returns None if the value
    should be deleted because nothing else remains.
    """
    fields = {k: v for k, v in parse_fields(raw or "").items() if k not in _OWN_FIELDS}
    if choice is None:
        return serialize_fields(fields) if fields else None
    own = {"SpecificAdapter": choice.specific_adapter_token, "GpuPreference": str(GPU_PREFERENCE_SPECIFIC)}
    return serialize_fields({**own, **fields})


def interpret(raw: str | None, discovery: DiscoveryResult) -> PreferredGpu:
    if raw is None:
        return PreferredGpu(PreferenceKind.NONE, None, discovery.default)
    fields = parse_fields(raw)
    try:
        pref = int(fields.get("GpuPreference", ""))
    except ValueError:
        return PreferredGpu(PreferenceKind.UNKNOWN, raw, None)
    kind = _CLASS_KINDS.get(pref, PreferenceKind.UNKNOWN)
    if kind is PreferenceKind.SPECIFIC:
        token = fields.get("SpecificAdapter", "").upper()
        matches = [g.key for g in discovery.gpus if g.key.specific_adapter_token == token]
        if len(matches) == 1:
            return PreferredGpu(kind, raw, matches[0], specific_token=token)
        # Not present (or ambiguous twins) → Windows silently falls back to its default.
        return PreferredGpu(kind, raw, None, specific_token=token, stale=not matches)
    resolved = {
        PreferenceKind.DEFAULT: discovery.default,
        PreferenceKind.POWER_SAVING: discovery.minimum_power,
        PreferenceKind.HIGH_PERFORMANCE: discovery.high_performance,
    }.get(kind)
    return PreferredGpu(kind, raw, resolved)
