# Spike S1 – Windows-Grafikpräferenz und „Bestimmte GPU“

Status: **erfolgreich** · 2026-11-17

Werkzeuge: Test-EXE `build/probe/gpucc-dxgi-probe.exe` (umbenannte Kopie von python.exe, `PYTHONHOME` auf die uv-Python-Installation) und [tools/spikes/s1_probe.py](../../tools/spikes/s1_probe.py). Das Skript gibt den DXGI-Standardadapter (`EnumAdapters1(0)`) des eigenen Prozesses aus.

## Teil 1 – Präferenzklassen [verifiziert]

| Registry-Wert für die Test-EXE | DXGI-Standardadapter beim nächsten Start |
|---|---|
| (kein Eintrag) | Intel Arc Pro B65 |
| `GpuPreference=1;` | AMD Radeon Graphics |
| `GpuPreference=2;` | Intel Arc Pro B65 |

- Die Präferenz verändert die Reihenfolge von `EnumAdapters1` für den Prozess → Apps, die einfach Adapter 0 bzw. den Standardadapter nehmen, folgen ihr.
- Sie wirkt beim **nächsten Prozessstart**. Es war kein Neustart von Windows nötig.
- Die Test-EXE eignet sich als **Selbsttest** für die App (z. B. nach Windows-Updates).
- Der Testeintrag wurde wieder entfernt.

## Teil 2 – „Bestimmte GPU“ [undokumentiert, beobachtet und verifiziert]

Die Einstellungen-App (System → Anzeige → Grafik → Optionen → RTX 3060) schrieb:

```
SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;
```

- `SpecificAdapter=<VendorId hex4>&<DeviceId hex4>&<SubSysId hex8>` – entspricht `DXGI_ADAPTER_DESC1` **ohne Revision und ohne PCI-Ort**.
- `GpuPreference=1073741824` (= `0x40000000`) kennzeichnet „bestimmter Adapter“.
- Andere Unterschlüssel unter `HKCU\Software\Microsoft\DirectX` wurden nicht angelegt.

Gegenprobe mit selbst geschriebenen Werten (Test-EXE, nächster Start):

| Selbst geschriebener Wert | DXGI-Standardadapter |
|---|---|
| `SpecificAdapter=1002&13C0&364E1849;GpuPreference=1073741824;` | AMD Radeon ✔ |
| `SpecificAdapter=8086&E222&60271849;GpuPreference=1073741824;` | Intel Arc Pro B65 ✔ |
| `SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;AutoHDREnable=1;` | NVIDIA RTX 3060 ✔ (Zusatzfelder stören nicht) |
| `SpecificAdapter=DEAD&BEEF&00000000;GpuPreference=1073741824;` (unbekannte GPU) | Intel Arc (**stiller Rückfall** auf den Standard) |

Danach wurde der Testeintrag wieder entfernt.

## Konsequenzen für die Implementierung

1. Backend `WindowsSpecificAdapter` kann jede der drei GPUs gezielt zuweisen → Auswahl im Overlay für **alle** GPUs möglich, nicht nur für die Klassen. Es bleibt als „experimentell“ markiert (undokumentiertes Format).
2. Vor dem Schreiben prüfen, ob die GPU aktuell vorhanden ist. Beim Lesen bestehender Einträge erkennen, wenn `SpecificAdapter` auf eine **nicht mehr vorhandene** GPU zeigt (stiller Rückfall!) → Warnung in der UI.
3. Zwei baugleiche Karten (gleiche Ven/Dev/SubSys) sind über dieses Format **nicht unterscheidbar** → in diesem Fall Option deaktivieren und erklären.
4. Selbsttest beim Start bzw. nach Windows-Updates: Die Test-EXE mit einem `SpecificAdapter`-Wert starten und prüfen, ob DXGI den erwarteten Adapter liefert. Schlägt der Test fehl, wird das Backend automatisch deaktiviert.
5. Für Arc und AMD bevorzugt weiterhin die dokumentierten Klassen `2` bzw. `1` schreiben, **wenn** die aktuelle DXGI-Reihenfolge sie genau dieser GPU zuordnet. `SpecificAdapter` nur verwenden, wenn keine Klasse passt (hier: NVIDIA) oder der Benutzer eine feste Bindung wünscht. *(Offen: ob immer `SpecificAdapter` einfacher und robuster ist – Entscheidung in Phase 3.)*
