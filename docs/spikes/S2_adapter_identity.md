# Spike S2 – GPU-Identität über DXGI + D3DKMT + SetupAPI + NVML

Status: **erfolgreich** · 2026-11-17 · Skript: [tools/spikes/s2_adapters.py](../../tools/spikes/s2_adapters.py)

## Ergebnis

Alle Aufrufe über reines `ctypes`, ohne Admin-Rechte, ohne nativen Helfer.

| GpuKey | DXGI-Beschreibung | VRAM (DXGI) | PCI (D3DKMT) | NVML |
|---|---|---|---|---|
| `PCI\VEN_8086&DEV_E222&SUBSYS_60271849&REV_00@03:00.0` | Intel Arc Pro B65 | 32 558 MiB | 03:00.0 | – |
| `PCI\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1@06:00.0` | NVIDIA GeForce RTX 3060 | 12 113 MiB | 06:00.0 | ✔ über PCI-Bus-ID |
| `PCI\VEN_1002&DEV_13C0&SUBSYS_364E1849&REV_C9@75:00.0` | AMD Radeon Graphics | 485 MiB (Carve-out) | 75:00.0 | – |

DXGI-Reihenfolge je Präferenz (für einen Prozess ohne eigene Präferenz):

- `UNSPECIFIED`: Arc, AMD, NVIDIA, Arc*, Basic Render
- `MINIMUM_POWER`: **AMD**, Arc, NVIDIA, …
- `HIGH_PERFORMANCE`: **Arc**, NVIDIA, AMD, …

→ Die Zuordnung „Energiesparen = AMD, Hohe Leistung = Arc“ ist bestätigt. Die NVIDIA ist über die Klassen nicht als erste GPU erreichbar.

## Erkenntnisse für die Implementierung

1. **Lokalisierte Strings nie parsen.** `SPDRP_LOCATION_INFORMATION` lautet auf diesem System „PCI-Bus 3, Gerät 0, Funktion 0“. Stattdessen `SPDRP_BUSNUMBER` (0x15) und `SPDRP_ADDRESS` (0x1C, `device << 16 | function`) verwenden.
2. **Zusätzlicher DXGI-Adapter „Intel Arc Pro B65“** mit LUID ohne PCI-Adresse (D3DKMT liefert `FFFFFFFF:FFFF.FFFF`). Hypothese: Adapter des Indirect-Display-Treibers „Meta Virtual Monitor“, der auf der Arc rendert. **Regel:** Ein DXGI-Adapter ohne gültige PCI-Adresse ist keine auswählbare GPU. Zusätzlich `DXGI_ADAPTER_FLAG_SOFTWARE` ausschließen (Basic Render Driver).
3. NVML-PCI-Bus-ID `00000000:06:00.0` ↔ D3DKMT `06:00.0` – Zuordnung eindeutig.
4. Die LUIDs (z. B. Arc `0x0000FEF3`) sind nur Laufzeitwerte und werden nicht gespeichert.
5. COM-vtable-Aufrufe per ctypes waren unproblematisch → **kein nativer Helfer nötig** (Architektur 3.8 entfällt vorerst).
