# ADR-0004: Performance- und Grafikanalyse (rechtes Ausklapp-Panel)

- Status: **angenommen** am 2026-11-19. Entscheidungen des Projektinhabers: Rechteabfrage **einmalig** beim ersten Öffnen des Analyse-Panels (Taste F oder Button); PresentMon **mitliefern**; externe Werkzeuge für Stufe D **erlaubt**; wichtigste APIs **DX12 und Vulkan** (→ RenderDoc zuerst, PIX für DX12 optional).
- Umgesetzt: Stufe A (Übersicht) und B (Frames, PresentMon 2.6.0). Offen: D (RenderDoc/PIX), danach C.
- Kontext: Wunsch nach einem rechts ausklappbaren Panel für Performance- und Grafikanalyse: die einzelnen
  **Passes** auf der Grafikkarte sehen und **framebasierte Performanceanalyse** durchführen.

## Was technisch möglich ist – und um welchen Preis

Die entscheidende Grenze: **Benannte Render-Passes** (z. B. „Shadow Map“, „GBuffer“, „Lighting“, „Post“) kennt
nur das Spiel selbst. Sichtbar werden sie nur, wenn sich ein Grafik-Debugger in den Spielprozess einklinkt
(RenderDoc, PIX, Nsight Graphics, Radeon GPU Profiler) **oder** das Spiel seine Marker über ETW meldet.
SetWhichGPU klinkt sich nach seinen Grundregeln **nie** in fremde Prozesse ein (AGENTS.md).

| Stufe | Was man sieht | Wie | Rechte | Eingriff ins Spiel |
|---|---|---|---|---|
| **A – Engines & Telemetrie** | Last je Engine der App (3D, Compute, Copy, Video) über 1–5 min, VRAM-Verlauf, Takt/Temperatur/Leistung | vorhandene Messung (PDH, NVML, IGCL), nur länger gespeichert | keine | keiner |
| **B – Frame-Analyse** | FPS, Frametime-Graph, 1 %/0,1 %-Lows, Frame-Pacing, **GPU-busy vs. Frametime** (GPU- oder CPU-limitiert), Anzeige-Latenz, Present-Modus (Flip/Independent Flip) | ETW-Ereignisse von DXGI/D3D/DxgKrnl, ausgewertet mit **Intel PresentMon** (MIT-Lizenz, mitgeliefert) | ETW-Echtzeitsitzung: Admin **oder** einmalig Mitglied der Gruppe „Leistungsprotokollbenutzer“ | keiner (nur Windows-Ereignisse) |
| **C – GPU-Zeitleiste je Frame** | pro Frame die GPU-Arbeitspakete je Engine/Queue (wie GPUView): Grafik- vs. Async-Compute-Überlappung, Leerlauflücken („Bubbles“), welche Prozesse dazwischenfunken | ETW DxgKrnl (DMA-/Queue-Paket-Ereignisse), eigener ETW-Consumer | wie B | keiner – aber **keine Pass-Namen**, nur Pakete |
| **D – Benannte Passes** | Pass-/Marker-Baum eines Frames mit GPU-Zeiten je Pass, Draw-Calls, Ressourcen | **externes Werkzeug** auf ausdrücklichen Klick: RenderDoc (MIT) oder PIX (kostenlos, D3D12) nimmt einen Frame auf; SetWhichGPU **liest die Aufnahme** danach aus (RenderDoc-Python-API) | keine | ja – durch das **externe** Werkzeug, vom Nutzer gestartet; Spiele mit Anti-Cheat (z. B. EAC) blockieren das |

### Hinweise je Stufe
- **B** ist der größte Nutzen für wenig Risiko: PresentMon ist der Industriestandard (auch Basis von CapFrameX,
  FrameView u. a.), funktioniert herstellerübergreifend und für DX9–12, Vulkan und OpenGL (über DXGI-Interop).
  Größe ca. 1–3 MB. Bei Spielen mit VRR/Frame-Generation sind die Werte sauber erklärbar (PresentMon liefert
  „displayed“ vs. „presented“).
- **C** ist aufwendig (eigener ETW-Parser für DxgKrnl-Ereignisse, hohe Ereignisrate) und zeigt nur
  Arbeitspakete, keine Pass-Namen. Wertvoll für Fortgeschrittene (Async Compute, Multi-GPU-Interferenz) –
  passt aber gut zum Kern von SetWhichGPU („wer arbeitet auf welcher GPU“).
- **D** liefert genau „die einzelnen Passes“, aber nur über ein externes Werkzeug. Für AGENTS.md hieße das:
  SetWhichGPU selbst injiziert weiterhin nichts; es darf ein installiertes Werkzeug **auf Nutzerklick**
  starten und dessen Aufnahmedateien lesen. Benannte Passes gibt es nur, wenn das Spiel Marker setzt
  (viele Engines tun das in Release-Builds nicht) – sonst gruppiert RenderDoc nach Render-Targets.

## Vorgeschlagenes UI

Rechts ausklappbares Panel (wie die Anwendungsliste links), Button „📈 Analyse“ im Kopf, Taste `F`.
Bezieht sich immer auf die gewählte Anwendung. Reiter:

1. **Übersicht** (A): Engine-Last gestapelt, VRAM, Takt/Leistung – Zeitfenster 30 s / 2 min / 5 min.
2. **Frames** (B): Live-Frametime-Graph mit GPU-busy-Linie, FPS/Lows, Ampel „GPU-limitiert / CPU-limitiert“,
   Aufnahme starten/stoppen → CSV-Export und Zusammenfassung.
3. **GPU-Zeitleiste** (C): Frame auswählen → Engines/Queues als Spuren mit Paketen, Prozesse farbig.
4. **Passes** (D): „Frame mit RenderDoc aufnehmen“ (nur wenn installiert), danach Pass-Liste mit GPU-Zeiten.

Farben je GPU wie im übrigen Overlay; alle Fremdtexte (Marker-Namen aus Aufnahmen) als reiner Text
(siehe ADR-0003, Sicherheitsregeln gelten sinngemäß für Aufnahme- und ETW-Daten).

## Empfohlene Reihenfolge

1. **A** (klein, ohne neue Rechte) – sofort machbar.
2. **B** mit PresentMon – größter Nutzen; Entscheidung zu Rechten nötig (siehe Fragen).
3. **D** als Integration von RenderDoc (optional PIX) – benannte Passes.
4. **C** zuletzt – aufwendig, Expertenfunktion.

## Offene Fragen an den Projektinhaber

1. **Rechte für B/C:** Admin-Abfrage pro Sitzung (wie der Spielmodus) **oder** einmalig den Benutzer zur Gruppe
   „Leistungsprotokollbenutzer“ hinzufügen (eine UAC-Abfrage, danach nie wieder; wirkt nach Neuanmeldung)?
2. **PresentMon mitliefern** (MIT, ~1–3 MB im Installer) – einverstanden?
3. **Externe Werkzeuge für D** (RenderDoc/PIX, die sich ins Spiel einklinken – auf Klick des Nutzers):
   AGENTS.md entsprechend ergänzen?
4. Welche Grafik-APIs/Spiele sind am wichtigsten (DX12, Vulkan, DX11)? Davon hängt ab, ob PIX zusätzlich lohnt.
