# Changelog

All notable changes are documented here. The project follows [Semantic Versioning](https://semver.org/) once it reaches 1.0.

## [Unreleased]

### Added
- Each graphics card has its own colour (NVIDIA green, AMD red, Intel blue, extra colours for a second card of a vendor): card name, total load and chart line; applications in the list take the colour of the GPU they run on
- Load chart per GPU (last 30 s) in the style of a download graph: whole graphics card vs. the selected application; the big number is now labelled "Total" and the app's share is shown separately
- Game libraries: the new per-user Epic Games Launcher (2026) and Meta Horizon Link / Oculus VR libraries
- Loaded local AI models (on by default, can be switched off in the tray menu): the overlay lists the models of Ollama, LM Studio/Bionic, Lemonade, KoboldCpp, llama.cpp, Stable Diffusion WebUI (A1111, Forge, SD.Next) and text-generation-webui next to the measured GPU – queried on 127.0.0.1 only (ADR-0003)
- Release workflow: the installer is built by GitHub Actions (manual run or tag `vX.Y.Z`); a tag creates a draft release with the installer and its SHA-256 checksum

### Security
- Local AI queries treat answers as hostile: fixed loopback URLs only, size cap, 3-second total deadline, deep-nesting protection, invisible/bidi characters stripped, plain-text display
- Launcher files are size-limited and executable paths must stay inside the game folder

## [0.1.0] – 2026-11-18

First installable release.

### Added
- Windows installer (`SetWhichGPU-0.1.0-setup.exe`): per-user install without administrator rights (all users optional), start with Windows, desktop shortcut, installer in English/German/Spanish/French. Updates close a running instance cleanly. Uninstall removes autostart, re-enables a GPU left disabled by game mode and optionally restores all GPU preferences SetWhichGPU changed
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
- The Microsoft Basic Display Adapter (PCs without a GPU driver, virtual machines) was listed as a GPU; implausible PCI locations are now rejected
- CUDA/OptiX load (e.g. Blender Cycles) was shown as 0 % because Windows' engine counters have no compute engine for NVIDIA; utilization now uses the maximum of all sources and NVML compute processes
