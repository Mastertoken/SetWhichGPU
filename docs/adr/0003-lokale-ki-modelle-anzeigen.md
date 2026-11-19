# ADR-0003: Geladene Modelle lokaler KI-Laufzeiten anzeigen (nur localhost)

- Status: **angenommen** (Freigabe durch den Projektinhaber am 2026-11-19; am selben Tag auf „standardmäßig
  eingeschaltet“ und alle sinnvollen Laufzeiten erweitert)
- Kontext: Wunsch, im Overlay zu sehen, *welches* KI-Modell gerade auf *welcher* GPU läuft.

## Problem

SetWhichGPU misst pro Prozess, welche GPU genutzt wird. Welches Modell ein Prozess wie `ollama.exe`
geladen hat, ist auf Prozessebene nicht sichtbar. Viele lokale KI-Programme verraten das über ihre lokale
HTTP-API. AGENTS.md verbot bisher jede Netzwerkverbindung „nach außen“.

## Entscheidung

Eine eng begrenzte Abfrage der lokalen APIs (Modul `gpucc.localai`):

1. **Standardmäßig eingeschaltet, abschaltbar:** Tray-Menü „Geladene KI-Modelle anzeigen“, Einstellung
   `localai` in der lokalen DB (`"0"` = aus).
2. **Nur Loopback:** ausschließlich `127.0.0.1` und `::1`; der Host ist nicht konfigurierbar (nur der Port).
   Kein Proxy, keine Redirects, nur `GET`, keine Nutzdaten, Timeout 1 s, Antwort max. 1 MiB.
   Es verlässt also nichts den PC.
3. **Nur bei Bedarf:** abgefragt wird nur, solange das Overlay offen ist **und** sein Ziel ein Prozess der
   jeweiligen Laufzeit ist (etwa alle 3 s), in einem eigenen Thread (UI-Thread blockiert nie).
4. **Antworten sind nicht vertrauenswürdig:** nur erwartete Felder, Steuerzeichen entfernt, Länge begrenzt,
   Modellpfade auf den Dateinamen gekürzt, Anzeige als reiner Text (kein Rich Text).
5. **Ehrlich getrennt:** Die Laufzeit liefert *welche* Modelle geladen sind; *welche GPU* wird weiterhin von
   SetWhichGPU gemessen und als „gemessen“ gekennzeichnet. Bei mehreren GPUs wird die gemessene Verteilung
   gezeigt, keine geratene Zuordnung Modell → GPU.

## Unterstützte Laufzeiten

| Laufzeit | Erkennung (Prozess) | Port (Standard) | Abfrage |
|---|---|---|---|
| Ollama | `ollama.exe`, `ollama app.exe`, `llama-server.exe` im Ollama-Ordner (ab 0.40) | 11434 / `OLLAMA_HOST` | `/api/ps` |
| LM Studio | `LM Studio.exe`, `lms.exe`, `llmster.exe` | aus `~/.lmstudio/.internal/http-server-config.json`, sonst 1234 | `/api/v1/models`, `/api/v0/models` |
| Bionic (neue LM-Studio-App) | `Bionic.exe` | aus `~/.lmstudio/apps/bionic/.internal/http-server-config.json`, sonst 1235 | wie LM Studio |
| Lemonade (AMD) | `lemonade-server.exe` u. a., `llama-server.exe`/`python.exe` im Lemonade-Ordner | 13305, 8000 | `/api/v1/health` |
| KoboldCpp | `koboldcpp*.exe` | 5001 | `/api/v1/model` |
| llama.cpp-Server | `llama-server.exe` (sonst) | 9931, 8080 / `LLAMA_ARG_PORT` | `/v1/models` (Router: nur `loaded`) |
| Stable Diffusion WebUI (A1111, Forge, reForge, SD.Next) | `python.exe` in Ordnern wie `stable-diffusion-webui`, `forge`, `automatic` | 7860, 7861 | `/sdapi/v1/options` (braucht `--api`) |
| text-generation-webui | `python.exe` im Ordner `text-generation-webui` | 5000 | `/v1/internal/model/info` (braucht `--api`) |

Weitere Ports je Laufzeit über `GPUCC_<NAME>_PORT`. Getestet am 2026-11-19 mit Ollama 0.40.16 (auch dessen
`llama-server.exe` mit dem llama.cpp-Parser) und Bionic; die übrigen nach Dokumentation mit Testantworten.

**Nicht unterstützt:** ComfyUI und InvokeAI (keine einfache Abfrage des geladenen Modells), Jan und Intel AI
Playground (Modell läuft in `llama-server.exe` auf wechselndem Port; Jans API verlangt einen Schlüssel),
GPT4All und LocalAI (melden nur installierte, nicht geladene Modelle), vLLM (unter Windows nur in WSL – dort
sieht Windows nur den VM-Prozess). Die GPU-Messung funktioniert für alle trotzdem.

## Sicherheit (Bedrohungsmodell)

Jedes lokale Programm kann einen dieser Ports belegen. Die Antworten gelten daher als **feindlich**:

| Risiko | Maßnahme |
|---|---|
| Anfrage an fremde Hosts (SSRF, Datenabfluss) | Host fest `127.0.0.1`/`::1`, Pfade nur aus der festen Liste der Laufzeiten, Port als Ganzzahl 1–65535; kein Proxy, keine Redirects, keine Nutzdaten, keine Cookies/Token |
| Speicher-/Zeit-DoS | Antwort ≤ 1 MiB, Timeout 1 s je Lesevorgang **und** 3 s Gesamtfrist (gegen tröpfelnde Server), eigener Thread mit „busy“-Sperre (keine Anfragenflut) |
| Parser-Angriffe | `json.loads` mit Abfangen von `ValueError` **und** `RecursionError` (tiefe Verschachtelung); nur erwartete Felder mit Typprüfung |
| HTML-/Rich-Text-Injektion im Overlay | alle Texte als `PlainText`-Labels; Namen nie in HTML, Registry, Dateien, Logs oder Shell-Befehle |
| Täuschung durch unsichtbare Zeichen | `gpucc.sanitize.clean_text`: Steuer-, Format- (z. B. U+202E), Private-Use-, Surrogat- und Zeilentrennzeichen entfernt, Länge begrenzt |
| Pfade in Antworten | Modellpfade werden auf den Dateinamen gekürzt (keine Benutzerpfade im Overlay) |

Dieselben Regeln gelten für Launcher-Dateien (Epic v2, Meta): Größenlimits, Typprüfung, und Startdateien
müssen im Spielordner liegen (keine absoluten Pfade, kein `..`). Nichts davon wird je ausgeführt.
Tests: `tests/unit/test_localai.py` (Abschnitt „hostile answers“), `tests/unit/test_launchers.py`.

## Folgen

- AGENTS.md: „keine Netzwerkverbindungen nach außen“ bleibt; Ausnahme ist nur diese Loopback-Abfrage.
- Datenschutzhinweis (Webseite, README) nennt die localhost-Abfrage und wie man sie abschaltet.
- API-Token (z. B. LM-Studio-Option „Require authentication“) werden nicht unterstützt; das Overlay sagt das.
