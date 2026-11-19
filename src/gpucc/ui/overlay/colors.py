"""One fixed text colour per graphics card, used everywhere the card appears (pure)."""

from __future__ import annotations

from gpucc.core.models import DiscoveryResult, GpuKey

# Vendor colours first (easy to remember), extra colours for a second card of the same vendor.
# Deliberately different from the UI's status colours (green "in use"/OK, amber warning, blue selection).
VENDOR_COLORS = {"nvidia": "#9BD84A", "amd": "#FF7B6E", "intel": "#5CB3FF"}
EXTRA_COLORS = ("#C792FF", "#FFB454", "#3DD6C6", "#FF8FD0", "#E6E07A")
FALLBACK = "#C8CCD2"
APP_COLOR = "#F2F3F5"  # the selected application's line in the load chart (neutral against every card colour)


PANEL_BG = (34, 36, 42)  # approximate overlay background the dimmed colours are mixed towards
DIM_FACTOR = 0.5


def dimmed(color: str, factor: float = DIM_FACTOR) -> str:
    """Darker shade of ``#RRGGBB`` (mixed towards the background) – an app that only holds GPU memory."""
    if len(color) != 7 or not color.startswith("#"):
        return color
    try:
        rgb = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    except ValueError:
        return color
    mixed = (round(c * factor + b * (1 - factor)) for c, b in zip(rgb, PANEL_BG, strict=True))
    return "#" + "".join(f"{c:02X}" for c in mixed)


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
