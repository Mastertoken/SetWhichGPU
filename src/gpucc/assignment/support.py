"""Which assignments are possible for an application (pure)."""

from __future__ import annotations

from gpucc.core.models import DiscoveryResult, Effect, GpuKey, Support, TargetApp
from gpucc.i18n import tr


def support_for(target: TargetApp | None, gpu: GpuKey | None, discovery: DiscoveryResult) -> Support:
    """Can ``target`` be assigned to ``gpu`` (None = Windows default) via the Windows preference?"""
    if target is None:
        return Support(False, Effect.UNSUPPORTED, tr("No application selected."))
    if not target.exe_path:
        if not target.running:
            return Support(
                False, Effect.UNSUPPORTED, tr("Game executable not known yet – start the game once to detect it.")
            )
        return Support(False, Effect.UNSUPPORTED, tr("Program path not readable (protected process)."))
    if target.is_uwp:
        return Support(
            False,
            Effect.UNSUPPORTED,
            tr("Store apps: please set the GPU under Settings → System → Display → Graphics."),
        )
    if gpu is not None:
        if target.exe_missing:
            return Support(False, Effect.UNSUPPORTED, tr("Program file no longer exists – only reset is possible."))
        if discovery.by_key(gpu) is None:
            return Support(False, Effect.UNSUPPORTED, tr("GPU is not present."))
        twins = [g for g in discovery.gpus if g.key.specific_adapter_token == gpu.specific_adapter_token]
        if len(twins) > 1:
            return Support(False, Effect.UNSUPPORTED, tr("Identical GPUs cannot be told apart by Windows."))
    return Support(True, Effect.NEXT_APP_START, tr("Takes effect the next time the application starts."))
