"""One fixed text colour per graphics card, used everywhere the card appears (pure)."""

from __future__ import annotations

from gpucc.core.models import DiscoveryResult, GpuKey

# Vendor colours first (easy to remember), extra colours for a second card of the same vendor.
# Deliberately different from the UI's status colours (green "in use"/OK, amber warning, blue selection).
VENDOR_COLORS = {"nvidia": "#9BD84A", "amd": "#FF7B6E", "intel": "#5CB3FF"}
EXTRA_COLORS = ("#C792FF", "#FFB454", "#3DD6C6", "#FF8FD0", "#E6E07A")
FALLBACK = "#C8CCD2"
APP_COLOR = "#F2F3F5"  # the selected application's line in the load chart (neutral against every card colour)


def gpu_colors(discovery: DiscoveryResult) -> dict[GpuKey, str]:
    """Stable per run: discovery order, vendor colour if still free, otherwise the next extra colour."""
    used: set[str] = set()
    extras = iter(EXTRA_COLORS)
    colors: dict[GpuKey, str] = {}
    for g in discovery.gpus:
        color = VENDOR_COLORS.get(g.vendor.value, "")
        if not color or color in used:
            color = next(extras, FALLBACK)
        used.add(color)
        colors[g.key] = color
    return colors
