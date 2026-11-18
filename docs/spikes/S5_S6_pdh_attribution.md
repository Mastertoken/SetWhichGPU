# Spikes S5 + S6 – PDH-Kosten und Zuordnung „tatsächlich genutzte GPU“

Status: **erfolgreich** · 2026-11-17
Skripte: [s5_s6_pdh.py](../../tools/spikes/s5_s6_pdh.py), [s6_e2e.py](../../tools/spikes/s6_e2e.py), [s6_d3d_load.py](../../tools/spikes/s6_d3d_load.py)

## S5 – Kosten

Abfrage von `\GPU Engine(*)\Utilization Percentage`, `\GPU Process Memory(*)\Dedicated Usage` und `\GPU Adapter Memory(*)\Dedicated Usage` in einer PDH-Query (`PdhAddEnglishCounterW` → sprachunabhängig, wichtig auf deutschem Windows):

| Messgröße | Wert |
|---|---|
| Engine-Instanzen | ~984 |
| Collect + Formatieren, Median / Max | 1,76 ms / 2,32 ms |
| CPU-Last des Prozesses bei 1-s-Intervall | nicht messbar (< 0,1 %) |

→ Ein 1-s-Intervall bei offenem Overlay ist unbedenklich. Im Hintergrund trotzdem auf 5 s oder „aus“ drosseln.

## S6 – Zuordnung

### Ende-zu-Ende-Test (Präferenz → Start → Beobachtung) [verifiziert]

Für die Test-EXE wurde nacheinander `SpecificAdapter` für jede GPU gesetzt. Die EXE erzeugt ein D3D11-Device auf dem **Standardadapter** und belegt Puffer. PDH ordnet den Prozess zu:

| Präferenz | DXGI-Standard in der App | PDH: Prozess-VRAM je GPU | Ergebnis |
|---|---|---|---|
| Intel Arc Pro B65 | Arc | Arc 260 MiB | ✔ |
| AMD Radeon | AMD | AMD 2 MiB | ✔ |
| NVIDIA RTX 3060 | NVIDIA | NVIDIA 8 MiB | ✔ |

Danach wurde der Registry-Zustand wiederhergestellt.

Beobachtung: NVIDIA und AMD belegen ungenutzte Puffer verzögert (nur wenige MiB), Arc belegt sofort. → Jede **von null verschiedene** Prozess-Speicherbelegung auf einem Adapter ist ein Nachweis. Die Höhe allein taugt nicht als Kriterium.

### Laufende Anwendungen (Leerlauf)

- Unity Editor (3 Prozesse) hatte im Leerlauf ~0 % 3D-Last, aber 1440 / 725 / 280 MiB VRAM **auf der Arc**. Unity Hub, Discord, VS Code und Chrome laufen ebenfalls auf der Arc.
- Weitere LUIDs: `0x0003675F` = virtueller Adapter (Meta Virtual Monitor, keine PCI-Adresse), `0x000104E9` = Microsoft Basic Render Driver (Software). Beide gehören nicht in die GPU-Auswahl.

## Konsequenzen für `monitoring.attribution`

Die Zuordnung prüft die Signale in dieser Reihenfolge:

1. **Aktivität:** Summe der Engines `3D` und `Compute*` je LUID über 2–3 Samples ≥ 0,5 % → `confidence=high`.
2. **Residenz:** keine Aktivität, aber Prozess-VRAM > 0 auf genau einer physischen GPU → `confidence=medium` („GPU-Speicher belegt, derzeit keine Last“).
3. Residenz auf mehreren GPUs → die mit der größten Belegung, `confidence=low`, alle GPUs anzeigen.
4. Nichts → „keine GPU-Nutzung erkennbar“.
5. Die Zuordnung erfolgt über den **Prozessbaum** (Unity: Editor + Worker; Chrome: GPU-Prozess). Aggregiert wird über die Ziel-PID und ihre Kindprozesse.
6. Kleine Copy-Engine-Last auf der Arc (Präsentation auf den Monitoren) nicht als Rendering werten.
7. Der Blender/OptiX-Fall (Compute auf der RTX) ist noch **nicht live beobachtet** – beim ersten Blender-Render nachholen und als Fixture aufzeichnen.
