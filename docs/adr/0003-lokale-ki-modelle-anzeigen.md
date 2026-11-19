# ADR-0003: Geladene Modelle lokaler KI-Laufzeiten anzeigen (localhost, opt-in)

- Status: **angenommen** (Freigabe durch den Projektinhaber am 2026-11-19)
- Kontext: Wunsch, im Overlay zu sehen, *welches* KI-Modell (Ollama, LM Studio, …) gerade auf *welcher* GPU läuft.

## Problem

SetWhichGPU misst pro Prozess, welche GPU genutzt wird. Welches Modell ein Prozess wie `ollama.exe`
geladen hat, ist auf Prozessebene nicht sichtbar. Ollama (`GET /api/ps`) und LM Studio
(`GET /api/v1/models`, älter `/api/v0/models`) verraten das über ihre lokale HTTP-API.
AGENTS.md verbietet bisher jede Netzwerkverbindung „nach außen“, und die Webseite verspricht „no network access“.

## Entscheidung

Eine eng begrenzte, **standardmäßig ausgeschaltete** Abfrage der lokalen APIs (Modul `gpucc.localai`):

1. **Opt-in:** Tray-Menü „Geladene KI-Modelle anzeigen“, Einstellung `localai` in der lokalen DB, Standard aus.
2. **Nur Loopback:** ausschließlich `127.0.0.1` und `::1`; der Host ist nicht konfigurierbar (nur der Port,
   aus `OLLAMA_HOST` bzw. `GPUCC_LMSTUDIO_PORT`). Kein Proxy, keine Redirects, nur `GET`, keine Nutzdaten,
   Timeout 1 s, Antwort max. 1 MiB.
3. **Nur bei Bedarf:** abgefragt wird nur, solange das Overlay offen ist **und** sein Ziel ein Prozess der
   jeweiligen Laufzeit ist (etwa alle 3 s), in einem eigenen Thread (UI-Thread blockiert nie).
4. **Antworten sind nicht vertrauenswürdig:** nur erwartete Felder, Steuerzeichen entfernt, Länge begrenzt,
   Anzeige als reiner Text (kein Rich Text).
5. **Ehrlich getrennt:** Die Laufzeit liefert *welche* Modelle geladen sind; *welche GPU* wird weiterhin von
   SetWhichGPU gemessen und als „gemessen“ gekennzeichnet. Bei mehreren GPUs wird die gemessene Verteilung
   gezeigt, keine geratene Zuordnung Modell → GPU.

Erkennung: Prozessname (`ollama.exe`, `LM Studio.exe`, `Bionic.exe`, …); Ollama ab 0.40 rechnet in einem
`llama-server.exe` im Ollama-Ordner. Port: Umgebungsvariable, sonst die `http-server-config.json` von
LM Studio/Bionic unter `~/.lmstudio`, sonst Standard (11434 / 1234 / 1235). Getestet am 2026-11-19 mit
Ollama 0.40.16 und Bionic.

ComfyUI wird nicht unterstützt: es bietet keine Abfrage des geladenen Modells.

## Folgen

- AGENTS.md: „keine Netzwerkverbindungen nach außen“ bleibt; Ausnahme ist nur diese Loopback-Abfrage.
- Datenschutzhinweis (Webseite, README) nennt die optionale localhost-Abfrage.
- Ein API-Token (LM-Studio-Option „Require authentication“) wird nicht unterstützt; das Overlay sagt das.
