# Security Policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's **private vulnerability reporting** ("Security" tab → "Report a vulnerability") on this repository. You will get an acknowledgement within 7 days.

Please include: affected version/commit, Windows build, steps to reproduce and the impact you expect.

## Scope

Security-relevant parts of SetWhichGPU:

- Writing to `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` and `HKCU\…\CurrentVersion\Run`
- Reading process information of other applications (path, version resource, GPU usage)
- Parsing untrusted local files (Steam `appinfo.vdf`/manifests, Epic manifests, Start Menu shortcuts)
- The **game mode helper** (`gpucc.gamemode.helper`, see `docs/adr/0002-…`), which runs **elevated** for the duration of a game session. It validates its arguments (PCI instance ID and executable name only) and calls `pnputil` exclusively with `/disable-device` or `/enable-device` – never `/force`, never `/remove-device`
- Any future local API / MCP server

## Design principles

- Runs **without administrator rights**; the only exception is the optional, user-started game mode (one UAC prompt per session)
- No driver modification, no DLL injection, no access to other processes' memory
- No network connections, no telemetry
- Every registry change is journaled before it is written and can be reverted
