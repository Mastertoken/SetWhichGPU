# Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added
- Tray app with `Ctrl+Alt+G` overlay, pin mode that follows the active application
- GPU discovery (DXGI + D3DKMT + SetupAPI) with stable PCI-based identity; virtual adapters filtered
- Monitoring: Windows GPU counters, NVML (NVIDIA), IGCL (Intel Arc); per-application attribution
- Per-app GPU selection via the Windows graphics preference (specific GPU, see ADR-0001), journaled and reversible
- "Restart required" only when the app predates the change; detection of apps that pick their GPU themselves
- Application list: running, background, saved, installed programs (Start Menu) and games (Steam, Epic, GOG)
- Autostart option
- Optional game mode for games that ignore the Windows preference (ADR-0002): temporarily disables the unwanted GPU while the game runs, always re-enables it
- UI in English, German, Spanish and French; language selectable in the tray menu
- Click on "GPU usage of the application" expands/collapses the per-GPU breakdown (previously only via `P`)

### Fixed
- Overlay was capped at 2/3 of the screen height, squeezing the GPU cards when the status text wrapped onto several lines
- Long program paths were clipped next to the header buttons instead of being shortened with "…"
- CUDA/OptiX load (e.g. Blender Cycles) was shown as 0 % because Windows' engine counters have no compute engine for NVIDIA; utilization now uses the maximum of all sources and NVML compute processes
