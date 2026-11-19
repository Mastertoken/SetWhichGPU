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
- The **frame-analysis permission helper** (`SetWhichGPU.exe --grant-perflog --user-sid <SID>`, see `docs/adr/0004-…`): runs elevated **once**, when the analysis panel is opened for the first time and the user agrees. It accepts only a plain user SID (`S-1-5-21-…`) and adds exactly that account to the built-in group *Performance Log Users* (`S-1-5-32-559`, addressed by SID, never by its localised name). Members can start event-tracing sessions; they get no other administrative rights. To undo it (as administrator): `Remove-LocalGroupMember -SID S-1-5-32-559 -Member <user>`
- **PresentMon** (Intel, MIT) is bundled for the frame analysis. SetWhichGPU starts it only if its SHA-256 matches the pinned value, never elevated, and parses its CSV output as untrusted input
- The **uninstall clean-up** (`SetWhichGPU.exe --uninstall`), which removes the autostart entry and, if confirmed, restores GPU preferences from the change journal
- Any future local API / MCP server

Note on per-user installs: the default installation folder (`%LOCALAPPDATA%\Programs\SetWhichGPU`) is writable by your user account, and game mode elevates that executable via UAC. If other software running under your account is not trusted, choose **"Install for all users"** in the installer (Program Files, write-protected).

## Design principles

- Runs **without administrator rights**; exceptions: the optional, user-started game mode (one UAC prompt per session) and the one-time frame-analysis permission (one UAC prompt, ever)
- No driver modification, no DLL injection, no access to other processes' memory
- No network connections except the optional loopback queries of local AI programs (ADR-0003), no telemetry
- Every registry change is journaled before it is written and can be reverted
