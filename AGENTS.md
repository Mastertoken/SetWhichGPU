# AGENTS.md – SetWhichGPU

Verbindliche Regeln für alle KI-Agenten (Codex CLI, Claude Code) und menschliche Mitwirkende.
Architektur-Referenz: [docs/architecture/PHASE1_ARCHITEKTUR.md](docs/architecture/PHASE1_ARCHITEKTUR.md).

## 1. Projekt in einem Satz

Windows-11-Tray-Anwendung (Python 3.13, PySide6), die per globalem Hotkey ein Overlay öffnet, GPUs überwacht und GPU-Präferenzen pro Anwendung **ehrlich** verwaltet: gespeicherte Präferenz und tatsächlich genutzte GPU sind immer getrennt.

## 2. Aktueller Stand

- Phasen 1–3 umgesetzt (Overlay, Monitoring, GPU-Zuweisung, Anwendungsliste); Vorbereitung einer Open-Source-Veröffentlichung läuft.
- Neue Funktionen und Phasen nur nach Freigabe durch den Projektinhaber. ADR-0002 (Spielmodus) ist **vorgeschlagen, nicht freigegeben**.

## 3. Architekturregeln

1. **Ports & Adapters.** `src/gpucc/core/` enthält nur reine Python-Modelle und `Protocol`-Schnittstellen und importiert weder `ctypes`, `winreg`, `pynvml` noch `PySide6`.
2. **ctypes/Win32 ausschließlich in `src/gpucc/platform/win32/`.** Andere Module nutzen deren typisierte Funktionen.
3. **Keine GPU-Indizes.** GPUs werden über `GpuKey` (PCI-Hardware-ID + PCI-Ort) identifiziert. LUID, NVML-Index, CUDA-Ordinal und DXGI-Reihenfolge sind Laufzeit-Bindungen und dürfen nie persistiert oder fest kodiert werden.
4. **Präferenz ≠ Beobachtung.** `PreferredGpu` und `ObservedGpu` nie zusammenführen, nie aus dem einen das andere ableiten.
5. **Ehrliche Fähigkeiten.** Jede Zuweisung liefert `Support(level, effect, reason)`. Die UI zeigt nicht unterstützte Optionen deaktiviert mit Begründung. Formulierungen wie „sofort umgeschaltet“ sind verboten, wenn der Effekt `NEXT_APP_START` ist.
6. **UI-Thread nie blockieren.** Telemetrie läuft im `MonitoringWorker` (QThread); Kommunikation nur über Qt-Signale mit unveränderlichen Dataclasses.
7. **Fehlende Hersteller-APIs sind Normalfall.** Jede `TelemetrySource` muss fehlende DLLs/Funktionen abfangen und Felder als „nicht verfügbar“ melden statt zu werfen.
8. Änderungen an `core/models.py` oder `core/ports.py` (gemeinsame Verträge) nur in einem eigenen Commit/Branch mit ADR unter `docs/adr/`.

## 4. Sicherheitsrichtlinien (nicht verhandelbar)

- Die Anwendung läuft **ohne Administratorrechte**. Keine Funktion bauen, die Elevation erfordert – **einzige Ausnahme: der Spielmodus nach ADR-0002.**
- **Keine** Treibermanipulation, keine NVIDIA-/Intel-/AMD-Treiberprofile, kein Übertakten. Geräte deaktivieren nur im Spielmodus (ADR-0002):
  - ausschließlich über `pnputil /disable-device` bzw. `/enable-device`, **niemals `/force`**, niemals `/remove-device`;
  - nur eine GPU **ohne angeschlossenen Monitor**, nie die letzte physische GPU, nie während auf ihr Compute-/Render-Last läuft;
  - nur nach ausdrücklicher Benutzeraktion + Bestätigungsdialog + UAC, sitzungsbezogen, immer mit automatischer Wiederherstellung (Spielende, Zeitlimit, Tray, Beenden, Absturz-Recovery beim nächsten Start);
  - der erhöhte Hilfsprozess (`gpucc.gamemode.helper`) akzeptiert nur validierte Instanz-IDs und Prozessnamen, keine freien Befehle;
  - jede Deaktivierung/Aktivierung wird protokolliert.
- **Kein** Hooking, keine DLL-Injection, kein Lesen/Schreiben fremden Prozessspeichers, kein Beenden fremder Prozesse.
- Erlaubte Schreibziele:
  - `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` – nur Einträge, die der Benutzer bestätigt hat; vorhandene Zusatzfelder im Wert (z. B. `AutoHDREnable=…;`) bleiben erhalten.
  - `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` – nur bei aktiviertem Autostart.
  - `%LOCALAPPDATA%\SetWhichGPU\`.
- **Jede** Registry-Änderung erzeugt einen `change_journal`-Eintrag (alter Wert, neuer Wert, Auslöser) **vor** dem Schreiben und muss rückgängig gemacht werden können.
- `DirectXUserGlobalSettings` (globale Standard-GPU) nie automatisch ändern.
- Keine systemweiten Umgebungsvariablen setzen; Compute-Geräteauswahl nur über Launch-Profile.
- Lokale API (Phase 5): nur Loopback/Named Pipe, Token-Auth, schreibende Aktionen benötigen Benutzerfreigabe.
- Keine Telemetrie-/Netzwerkverbindungen nach außen. Einzige Netzwerkfunktion: die abschaltbare Abfrage
  lokaler KI-Laufzeiten ausschließlich über Loopback (ADR-0003, `gpucc.localai`) – nie ein anderer Host.
- **Keine persönlichen Daten im Repo:** keine Benutzernamen, E-Mail-Adressen, Benutzerpfade, Projektnamen oder gerätespezifischen Kennungen (PnP-Instanz-IDs, GPU-UUIDs, Steam-IDs) in Code, Tests, Fixtures oder Doku. Fixtures anonymisieren (Modellkennungen VEN/DEV/SUBSYS sind erlaubt). Öffentliche Releases nur über `tools/release/export_public.ps1` (Datenschutz-Scan + frische Historie).
- Bei Tests auf dem echten System: **keine** Schreibtests gegen die echte Registry. Registry-Zugriffe in Tests über Fake oder einen eigenen Test-Unterschlüssel (`HKCU\Software\SetWhichGPUTest`), der im Teardown gelöscht wird.

## 5. Werkzeuge und Befehle

```powershell
uv sync                                   # Abhängigkeiten installieren
uv run python -m gpucc                    # Anwendung starten
uv run pytest                             # Unit-Tests (laufen ohne GPU-Hardware)
uv run pytest -m windows                  # Integrationstests gegen echte Windows-APIs (nur lesend)
$env:GPUCC_HW_TESTS='1'; uv run pytest -m hardware   # Tests gegen echte GPUs
uv run ruff check . ; uv run ruff format --check .
uv run mypy src                           # strict
```

Vor jedem Commit müssen `ruff check`, `ruff format --check`, `mypy src` und `pytest` grün sein.

## 6. Code-Konventionen

- Python 3.13, vollständige Type Hints, `mypy --strict` für `src/`.
- Dataclasses `frozen=True, slots=True` für Modelle; `Enum` statt String-Konstanten.
- Logging über `logging` mit strukturierten Feldern (`extra={...}`); keine `print`-Ausgaben. Logdatei rotierend unter `%LOCALAPPDATA%\SetWhichGPU\logs\`.
- Keine stummen `except Exception: pass`. Erwartete Plattformfehler in eigene Exceptions aus `core/errors.py` übersetzen.
- Code-Bezeichner, Docstrings und Logmeldungen auf Englisch.
- UI-Texte: englische Quelltexte über `tr("…")` aus `gpucc.i18n`; die deutsche Übersetzung gehört in `src/gpucc/i18n/de.py` (`tests/unit/test_i18n.py` prüft Vollständigkeit und Platzhalter). Keine zusammengesetzten Sätze aus Einzelteilen – ganze Sätze mit `{platzhaltern}` übersetzen.
- Öffentliche Projektdateien (README, CONTRIBUTING, SECURITY, CHANGELOG) auf Englisch; interne Architektur-/Spike-Dokumente dürfen Deutsch bleiben.
- Neue Abhängigkeiten nur mit Begründung im Commit; bevorzugt Standardbibliothek/ctypes.

## 7. Tests

- `tests/unit/`: Fakes für alle Ports, keine echten Win32-Aufrufe; müssen auch in CI ohne GPU laufen.
- `tests/integration/` (`@pytest.mark.windows`): echte Win32-Aufrufe, **nur lesend**.
- `tests/hardware/` (`@pytest.mark.hardware`): nur mit `GPUCC_HW_TESTS=1`.
- `tests/fixtures/`: aufgezeichnete Daten (PDH-Instanzen, NVML-Werte, Registry-Strings) dieses Zielsystems für reproduzierbare Tests.
- UI-Tests mit `pytest-qt`.
- Jede Fehlerkorrektur bekommt einen Regressionstest.

## 8. Zusammenarbeit über Git-Worktrees (Codex CLI + Claude Code)

- `main` ist immer lauffähig. Gearbeitet wird in Worktrees:
  ```powershell
  git worktree add ..\gpucc-claude-<thema> -b claude/<thema>
  git worktree add ..\gpucc-codex-<thema>  -b codex/<thema>
  ```
- Branch-Präfix kennzeichnet den Agenten: `claude/…`, `codex/…`, `human/…`.
- **Ein Modul, ein Agent:** Vor Beginn in `docs/WORKBOARD.md` eintragen, welches Modul/Verzeichnis bearbeitet wird. Keine parallelen Änderungen am selben Modul.
- Gemeinsame Verträge (`core/models.py`, `core/ports.py`, DB-Migrationen, `pyproject.toml`) nur in eigenen, kleinen Branches ändern, die zuerst gemergt werden. Andere Branches rebasen danach.
- Kleine, thematisch saubere Commits; Commit-Nachricht im Format `<modul>: <was und warum>`.
- Kein Force-Push auf `main`, keine Commits direkt auf `main` durch Agenten. Merge nur nach grünen Checks und Freigabe durch den Projektinhaber.
- Jeder Worktree hat ein eigenes `.venv` (`uv sync` im Worktree ausführen); die SQLite-Datenbank für Entwicklung über `GPUCC_DATA_DIR` auf ein worktree-lokales Verzeichnis umleiten, damit Instanzen sich nicht gegenseitig stören.
- Spike-Ergebnisse unter `docs/spikes/`, Architekturentscheidungen als ADR unter `docs/adr/NNNN-titel.md`.

## 9. Wenn du unsicher bist

- Ist ein API-Verhalten undokumentiert, implementiere es hinter einem Feature-Flag, kennzeichne es in der UI als „experimentell“ und dokumentiere die Beobachtung in `docs/spikes/`.
- Lieber eine Funktion als „nicht unterstützt“ anzeigen als eine unzuverlässige Zuweisung versprechen.
- Bei Konflikten mit diesen Regeln: anhalten und den Projektinhaber fragen.
