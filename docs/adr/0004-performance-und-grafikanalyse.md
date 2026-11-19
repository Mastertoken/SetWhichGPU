# ADR-0004: Performance- und Grafikanalyse (rechtes Ausklapp-Panel)

- Status: **angenommen** am 2026-11-19. Entscheidungen des Projektinhabers: Rechteabfrage **einmalig** beim ersten Öffnen des Analyse-Panels (Taste F oder Button); PresentMon **mitliefern**; externe Werkzeuge für Stufe D **erlaubt**; wichtigste APIs **DX12 und Vulkan** (→ RenderDoc zuerst, PIX für DX12 optional).
- Umgesetzt: Stufen A und B, D mit lokalem RenderDoc-Replay und C als Import von Zeitspuren. Der direkte ETW-Live-Consumer für C steht aus.
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

### Bedienung der implementierten Stufen C und D

- **GPU-Zeitleiste → Trace importieren** öffnet lokal gespeicherte Zeitspuren. Frame-IDs wählen ein
  aus den markierten Intervallen abgeleitetes Zeitfenster. Andere Spuren bleiben darin sichtbar.
  Zoom und Positionsregler dienen zur Navigation. Farben gruppieren Prozesse, die Zeitabdeckung misst
  die Vereinigung der angezeigten Intervalle je Spur. Lücken können auch durch fehlende Trace-Daten entstehen.
- **Echtzeit-3D:** Nsight-Systems-SQLite-Exporte können DXGI-Aufrufe mit Frame-ID, Vulkan-Workloads und
  gepaarte WDDM-DMA-Ereignisse enthalten. Ein DXGI-Frame-Fenster beschreibt die markierten Aufrufzeiten.
  DMA-Balken erscheinen nur für passende Start-/Stop-Ereignisse. Die Prozesszuordnung verwendet eindeutige
  Queue-Submit-Daten. Hardware und Aufnahmeoptionen bestimmen, welche Tabellen vorhanden sind.
- **KI-Inferenz und Bildrendering:** PyTorch-Profiler-Exporte aus `export_chrome_trace()` liefern CPU-Operatoren
  und aufgezeichnete Geräteaktivität. Nsight-Systems-SQLite-Exporte (`nsys export --type sqlite ...`) liefern
  CUDA-Kernel, Kopien, Speicherinitialisierungen und NVTX-Bereiche. Chrome-JSON unterstützt vollständige
  Intervalle (`X`) und gepaarte Start-/Ende-Ereignisse (`B`/`E`, Zeit in µs). Für JSON und CSV ist gzip möglich.
- **Eigene Zeitspuren:** UTF-8-CSV mit den Pflichtspalten `start_us,end_us,engine,process` und den optionalen
  Spalten `gpu,queue,name,frame`. Windows Performance Analyzer kann ETW-Tabellen als CSV exportieren.
  Spalten und Einheiten werden vor dem Import auf dieses Schema umgesetzt. Für genaue Frame-Grenzen
  kann die Datei ein eigenes Intervall mit dem gewünschten Frame-Label enthalten.
- **Render-Passes:** RenderDoc per Klick öffnen, dort eine DX12- oder Vulkan-Anwendung aufnehmen und die
  lokale `.rdc`-Datei über **Aufnahme importieren** laden. Der Unterprozess liest beim Replay Marker,
  Draws, Dispatches, Render-Targets und verfügbare GPU-Zeiten. Die Zeiten stammen vom Replay auf dem
  lokalen System. Fehlende Marker oder Messwerte bleiben als solche erkennbar. PIX bleibt optional.
- Importgrenzen: 32 MiB unkomprimierter Text, maximal 200.000 Trace-Intervalle, maximal 2.000 gezeichnete
  Intervalle pro Ansicht und 5.000 Aktionen pro Capture. SQLite wird schreibgeschützt geöffnet.

### Ursprüngliche Reihenfolge

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
