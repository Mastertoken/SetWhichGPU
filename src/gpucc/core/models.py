"""Domain models shared by all modules.

GPU identity is a :class:`GpuKey` (PCI hardware id + PCI location). Runtime bindings such as
LUIDs, NVML handles or CUDA ordinals are never part of persisted identity.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

# ----------------------------------------------------------------------------- GPU identity


class Vendor(StrEnum):
    NVIDIA = "nvidia"
    INTEL = "intel"
    AMD = "amd"
    OTHER = "other"

    @classmethod
    def from_pci_id(cls, vendor_id: int) -> Vendor:
        return {0x10DE: cls.NVIDIA, 0x8086: cls.INTEL, 0x1002: cls.AMD}.get(vendor_id, cls.OTHER)


_PCI_RE = re.compile(r"^([0-9A-Fa-f]{2,4}):([0-9A-Fa-f]{2})\.([0-7])$")


@dataclass(frozen=True, slots=True, order=True)
class PciAddress:
    bus: int
    device: int
    function: int

    def __str__(self) -> str:
        return f"{self.bus:02X}:{self.device:02X}.{self.function}"

    @classmethod
    def parse(cls, text: str) -> PciAddress:
        m = _PCI_RE.match(text.strip())
        if not m:
            raise ValueError(f"invalid PCI address: {text!r}")
        return cls(int(m[1], 16), int(m[2], 16), int(m[3]))


_KEY_RE = re.compile(
    r"^PCI\\VEN_([0-9A-F]{4})&DEV_([0-9A-F]{4})&SUBSYS_([0-9A-F]{8})&REV_([0-9A-F]{2})@(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, order=True)
class GpuKey:
    """Stable GPU identity: PCI ids plus PCI location (distinguishes identical cards)."""

    vendor_id: int
    device_id: int
    subsys_id: int
    revision: int
    pci: PciAddress

    def __str__(self) -> str:
        return f"{self.hardware_id}@{self.pci}"

    @property
    def hardware_id(self) -> str:
        return (
            f"PCI\\VEN_{self.vendor_id:04X}&DEV_{self.device_id:04X}"
            f"&SUBSYS_{self.subsys_id:08X}&REV_{self.revision:02X}"
        )

    @property
    def specific_adapter_token(self) -> str:
        """Token used by Windows' per-app ``SpecificAdapter=`` preference (no revision/location)."""
        return f"{self.vendor_id:04X}&{self.device_id:04X}&{self.subsys_id:08X}"

    @classmethod
    def parse(cls, text: str) -> GpuKey:
        m = _KEY_RE.match(text.strip())
        if not m:
            raise ValueError(f"invalid GpuKey: {text!r}")
        return cls(int(m[1], 16), int(m[2], 16), int(m[3], 16), int(m[4], 16), PciAddress.parse(m[5]))


@dataclass(frozen=True, slots=True)
class GpuInfo:
    key: GpuKey
    name: str
    vendor: Vendor
    luid: int  # runtime binding only – changes across reboots/driver restarts
    dedicated_vram_bytes: int
    shared_memory_bytes: int
    is_integrated: bool
    instance_id: str = ""
    driver_version: str | None = None

    @property
    def short_name(self) -> str:
        n = self.name.replace("(R)", "").replace("(TM)", "")
        for prefix in ("NVIDIA ", "Intel ", "AMD "):
            n = n.removeprefix(prefix)
        return " ".join(n.replace("Graphics", "").split()) or self.name


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    gpus: tuple[GpuInfo, ...]
    #: GPU Windows hands out for GpuPreference=2 / =1 / no preference (from DXGI ordering).
    high_performance: GpuKey | None = None
    minimum_power: GpuKey | None = None
    default: GpuKey | None = None
    ignored: tuple[str, ...] = ()
    #: GPUs with at least one attached monitor – never disabled by game mode.
    display_gpus: frozenset[GpuKey] = frozenset()

    def by_key(self, key: GpuKey) -> GpuInfo | None:
        return next((g for g in self.gpus if g.key == key), None)

    def by_luid(self, luid: int) -> GpuInfo | None:
        return next((g for g in self.gpus if g.luid == luid), None)


# ----------------------------------------------------------------------------- telemetry


@dataclass(frozen=True, slots=True)
class GpuReading:
    """Partial reading from one telemetry source; ``None`` means 'not available from here'."""

    utilization_pct: float | None = None
    engines: Mapping[str, float] = field(default_factory=dict)
    vram_used_bytes: int | None = None
    temperature_c: float | None = None
    power_w: float | None = None


@dataclass(frozen=True, slots=True)
class ProcessGpuUsage:
    pid: int
    key: GpuKey
    engines: Mapping[str, float]
    dedicated_bytes: int


@dataclass(frozen=True, slots=True)
class SourceSample:
    readings: Mapping[GpuKey, GpuReading] = field(default_factory=dict)
    processes: tuple[ProcessGpuUsage, ...] = ()


@dataclass(frozen=True, slots=True)
class GpuTelemetry:
    key: GpuKey
    utilization_pct: float | None
    engines: Mapping[str, float]
    vram_used_bytes: int | None
    vram_total_bytes: int
    temperature_c: float | None
    power_w: float | None
    sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GpuSnapshot:
    timestamp: float
    gpus: tuple[GpuTelemetry, ...]
    processes: tuple[ProcessGpuUsage, ...]

    def for_gpu(self, key: GpuKey) -> GpuTelemetry | None:
        return next((g for g in self.gpus if g.key == key), None)


# ----------------------------------------------------------------------------- applications


#: Longer file descriptions ("Notepad++ : a free (GNU) source code editor") fall back to ProductName.
MAX_DESCRIPTION_LEN = 32


class FullscreenState(StrEnum):
    NONE = "none"
    BORDERLESS = "borderless"  # QUNS_BUSY – overlay works
    EXCLUSIVE = "exclusive"  # QUNS_RUNNING_D3D_FULL_SCREEN – overlay not possible
    PRESENTATION = "presentation"


@dataclass(frozen=True, slots=True)
class TargetApp:
    hwnd: int
    pid: int
    exe_path: str | None
    title: str
    window_class: str
    product_name: str | None = None
    file_description: str | None = None
    company: str | None = None
    monitor_origin: tuple[int, int] | None = None
    fullscreen: FullscreenState = FullscreenState.NONE
    access_denied: bool = False
    is_uwp: bool = False
    started_at: float | None = None  # process creation time (epoch seconds)
    exe_missing: bool = False  # saved entry whose executable no longer exists
    label: str | None = None  # e.g. the game's store name ("Age of Mythology: Retold")
    exe_note: str | None = None  # how the exe was determined (installed games)

    @property
    def running(self) -> bool:
        return self.pid != 0

    @property
    def app_key(self) -> str:
        """Identity of the *application* (case-insensitive exe path), stable across restarts."""
        return (self.exe_path or f"pid:{self.pid}").lower()

    @property
    def exe_name(self) -> str:
        if not self.exe_path:
            return "?"
        return self.exe_path.replace("/", "\\").rsplit("\\", 1)[-1]

    @property
    def display_name(self) -> str:
        if self.label:
            return self.label
        desc = (self.file_description or "").strip()
        product = (self.product_name or "").strip()
        if desc and (len(desc) <= MAX_DESCRIPTION_LEN or not product):
            return desc
        if product:
            return product
        if self.exe_path:
            return self.exe_name.rsplit(".", 1)[0]
        return self.title or f"PID {self.pid}"


# ----------------------------------------------------------------------------- observation


class Confidence(StrEnum):
    HIGH = "high"  # measurable render/compute activity
    MEDIUM = "medium"  # GPU memory resident on exactly one GPU, no activity
    LOW = "low"  # memory on several GPUs, no activity
    NONE = "none"  # no GPU usage visible


@dataclass(frozen=True, slots=True)
class ProcessGpuSummary:
    key: GpuKey
    render_pct: float
    dedicated_bytes: int
    engines: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class ObservedGpu:
    """What the app is *measured* to use. Never derived from a stored preference."""

    key: GpuKey | None
    confidence: Confidence
    per_gpu: tuple[ProcessGpuSummary, ...] = ()


# ----------------------------------------------------------------------------- preferences


class PreferenceKind(StrEnum):
    NONE = "none"  # no entry → Windows decides
    DEFAULT = "default"  # GpuPreference=0
    POWER_SAVING = "power_saving"  # GpuPreference=1
    HIGH_PERFORMANCE = "high_performance"  # GpuPreference=2
    SPECIFIC = "specific"  # SpecificAdapter=…;GpuPreference=1073741824
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PreferredGpu:
    """The *stored* Windows graphics preference for an executable."""

    kind: PreferenceKind
    raw: str | None
    key: GpuKey | None  # resolved GPU, if determinable
    specific_token: str | None = None
    stale: bool = False  # SpecificAdapter points to a GPU that is not present

    @property
    def is_own_preference(self) -> bool:
        """True if the entry actually pins the app to a GPU (class or specific adapter)."""
        return self.kind in (PreferenceKind.SPECIFIC, PreferenceKind.POWER_SAVING, PreferenceKind.HIGH_PERFORMANCE)

    @property
    def choice(self) -> GpuKey | None:
        """The option the overlay should show as current: a GPU, or None for 'Windows-Standard'."""
        return self.key if self.is_own_preference and not self.stale else None


# ----------------------------------------------------------------------------- assignment


class Effect(StrEnum):
    NEXT_APP_START = "next_app_start"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Support:
    supported: bool
    effect: Effect
    reason: str = ""


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """One registry change made by SetWhichGPU (written *before* the change)."""

    id: int
    ts: float
    exe_path: str
    old_value: str | None
    new_value: str | None
    trigger: str  # "overlay" | "revert" | later "api"
    status: str  # "pending" | "applied" | "failed" | "skipped"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ApplyResult:
    changed: bool
    old_value: str | None
    new_value: str | None
    journal_id: int | None
    applied_at: float


@dataclass(frozen=True, slots=True)
class RevertReport:
    reverted: tuple[str, ...]
    conflicts: tuple[str, ...]  # changed outside SetWhichGPU → left untouched
    failed: tuple[str, ...]
