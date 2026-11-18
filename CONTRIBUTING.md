# Contributing

Thanks for helping! SetWhichGPU deals with very different hardware, so good bug reports matter most.

## Reporting bugs

Please use the issue template and include:

- **GPUs** (model + vendor of each card, which one drives your monitors), laptop or desktop
- **Windows build** (`winver`) and whether "Hardware-accelerated GPU scheduling" is on
- What you expected, what happened, and the application involved
- The log file from the tray menu → "Open log folder" (`gpucc.log`). It contains executable paths – remove anything you consider private

Before reporting "the GPU preference does not work", please check the README section *What it can and cannot do*: many applications pick their GPU themselves.

## Development setup

```powershell
uv sync
uv run pytest ; uv run pytest -m windows
uv run ruff check . ; uv run ruff format --check . ; uv run mypy src
```

All four must pass before a pull request is merged.

## Rules

The binding project rules are in [AGENTS.md](AGENTS.md) (architecture, safety rules, tests). The short version:

- Platform code (`ctypes`, Win32) only in `src/gpucc/platform/win32/`; `src/gpucc/core/` stays pure
- No hard-coded GPU indices – GPUs are identified by PCI id + location
- Stored preference and observed GPU are never mixed
- No admin rights, no driver changes, no injection; every registry write is journaled
- UI text: English source strings via `tr("…")`; add the German translation to `src/gpucc/i18n/de.py` (a test checks this)
- Tests never write to the real `UserGpuPreferences` key – use fakes or `HKCU\Software\SetWhichGPUTest`

## Code of conduct

Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).
