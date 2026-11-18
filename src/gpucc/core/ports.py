"""Port protocols implemented by platform adapters (and by fakes in tests)."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from gpucc.core.models import DiscoveryResult, GpuInfo, SourceSample, TargetApp


class GpuDiscovery(Protocol):
    def scan(self) -> DiscoveryResult: ...


class TelemetrySource(Protocol):
    """One telemetry backend (PDH, NVML, IGCL …). Missing APIs are normal, not errors."""

    name: str

    @property
    def available(self) -> bool: ...

    def bind(self, gpus: Sequence[GpuInfo]) -> None:
        """(Re)map the source's devices to the discovered GPUs."""

    def sample(self) -> SourceSample: ...

    def close(self) -> None: ...


class ForegroundProbe(Protocol):
    def capture(self) -> TargetApp | None: ...

    def capture_window(self, hwnd: int, with_state: bool = False) -> TargetApp | None: ...

    def running_apps(self) -> list[TargetApp]:
        """Applications with a visible top-level window."""
        ...

    def background_apps(self, pids: Iterable[int], exclude: Iterable[int] = ()) -> list[TargetApp]:
        """Windowless, non-system processes among ``pids``."""
        ...

    def describe_exe(self, exe_path: str) -> TargetApp:
        """A not-running application (pid 0)."""
        ...

    def process_tree(self, pid: int) -> frozenset[int]:
        """``pid`` plus all its descendants."""
        ...

    def parent_map(self) -> dict[int, int]: ...


class PreferenceReader(Protocol):
    def read(self, exe_path: str) -> str | None:
        """Raw value of HKCU\\…\\DirectX\\UserGpuPreferences for ``exe_path``."""
        ...


class PreferenceRegistry(PreferenceReader, Protocol):
    """Read/write access to the per-app Windows graphics preference (HKCU only)."""

    def entries(self) -> dict[str, str]:
        """All stored preferences: exe path → raw value."""
        ...

    def write(self, exe_path: str, value: str) -> None: ...

    def delete(self, exe_path: str) -> None: ...
