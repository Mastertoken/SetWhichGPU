# Spike S3 – Intel-Arc-Telemetrie über IGCL

Status: **erfolgreich** · 2026-11-17 · Skript: [tools/spikes/s3_igcl.py](../../tools/spikes/s3_igcl.py)

`C:\Windows\System32\ControlLib.dll` 1.2.298.0 (kommt mit dem Intel-Treiber 32.0.101.8976). Aufruf über `ctypes`, **ohne Admin-Rechte**, `ctlInit` mit `CTL_INIT_FLAG_USE_LEVEL_ZERO`, API-Version 1.1.

## Messwerte Arc Pro B65 (Leerlauf mit Desktop/Discord/VS Code)

| Feld | Wert | Hinweis |
|---|---|---|
| GPU-Temperatur | 40 °C | direkt |
| VRAM-Temperatur | 42 °C | direkt |
| GPU-Leistung | ~29 W | aus `gpuEnergyCounter` (J) / `timeStamp` (s), Differenz zweier Samples |
| Kartenleistung gesamt | – | `totalCardEnergyCounter` meldet „unterstützt“, bleibt aber 0 → als **nicht verfügbar** werten |
| Auslastung global / Render | 12,9 % / 6,3 % | aus Aktivitätszählern (Differenz) |
| GPU-Takt / Spannung | 2400 MHz / 0,945 V | direkt |
| VRAM-Takt | 2375 MHz | direkt |
| Lüfter | 1079 U/min | `fanSpeed[0]` |
| Aufrufdauer | 0,2 ms | |

## Erkenntnisse

1. Struktur-Layouts aus `igcl_api.h` funktionieren mit ctypes (`ctl_power_telemetry_t` Version 1 = 1024 Byte). Bei abweichender Treiberversion `Size`/`Version` prüfen und Rückgabecodes behandeln.
2. `ctlGetDeviceProperties` liefert über `pDeviceID` die **LUID** (`0x0000FEF3`) und die PCI-BDF (`03:00.0`) → Zuordnung zum `GpuKey` eindeutig.
3. Subsystem-ID: IGCL meldet `pci_subsys_vendor_id = 1849`, `pci_subsys_id = 6027`; DXGI kombiniert zu `0x60271849` (`id << 16 | vendor`).
4. Leistung und Auslastung sind **Zähler** → die TelemetrySource muss den vorherigen Wert halten und Differenzen bilden; das erste Sample liefert keine Leistung.
5. Felder mit `bSupported = true`, aber konstant 0 (Kartenleistung) über eine Plausibilitätsregel ausblenden.
6. Kein nativer Helfer nötig.
