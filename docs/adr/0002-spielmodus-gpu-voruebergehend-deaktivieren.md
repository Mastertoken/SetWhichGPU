# ADR-0002: Spielmodus – eine GPU vorübergehend deaktivieren

Status: **angenommen** · vorgeschlagen und vom Projektinhaber freigegeben am 2026-11-18

Umsetzungsdetail (ergänzt bei der Implementierung): Der Hilfsprozess deaktiviert die GPU erst, **nachdem das Spiel beendet wurde** – ein Gerät, das gerade rendert, lässt sich nicht ohne Neustart deaktivieren. Ablauf: Spiel beenden → GPU aus → Spiel neu starten → Spielende → GPU an.

## Kontext

Manche Anwendungen ignorieren die Windows-Grafikpräferenz und wählen ihre GPU selbst. Belegter Fall: *Age of Mythology: Retold* (`MythLog.txt`):

```
Adapter[0]: Intel(R) Arc(TM) Pro B65 Graphics; GFLOPs: 768      ← Windows-Präferenz wirkt (Index 0)
Adapter[2]: NVIDIA GeForce RTX 3060; GFLOPs: 15052
Adapter index chosen: 2                                           ← Spiel nimmt die "stärkste" GPU
```

Das Spiel bewertet die Arc Pro B65 falsch und bietet keine Einstellung oder Startoption für den Adapter. Der einzige zuverlässige Weg, die Arc zu erzwingen: **Die RTX ist für das Spiel nicht vorhanden.** Der Benutzer wünscht dafür eine Funktion in SetWhichGPU.

Verworfen wird eine Ersatz-`dxgi.dll` im Spielordner (DLL-Proxy/Hooking): Das ist ein Eingriff in das Spiel, birgt Sperrgefahr durch die Xbox-/PlayFab-Onlinedienste und bleibt Nicht-Ziel.

## Entscheidung (Vorschlag)

Ein **opt-in „Spielmodus“ pro Anwendungsprofil**, der eine **nicht anzeigende** GPU für die Dauer einer Spielsitzung über das Windows-Bordmittel `pnputil` deaktiviert und danach automatisch wieder aktiviert.

### Ablauf

1. Im Overlay erscheint bei Status „wählt ihre GPU selbst“ zusätzlich die Aktion **„Spielmodus: NVIDIA RTX 3060 während des Spielens deaktivieren …“**.
2. Vorprüfungen (siehe Sicherheitsregeln). Danach ein Bestätigungsdialog, der die Folgen nennt (Blender/CUDA solange ohne NVIDIA).
3. **Eine UAC-Abfrage** startet einen kleinen, erhöhten Hilfsprozess `gpucc-gamemode` (eigenes Modul, keine UI). Er:
   1. ruft `pnputil /disable-device "<Instanz-ID>"` auf (**niemals `/force`**),
   2. prüft, ob das Gerät wirklich deaktiviert ist (sonst sofort Abbruch und Re-Aktivierung),
   3. wartet, bis der Spielprozess (`AoMRT_s.exe`) startet und wieder endet (Startfrist z. B. 10 Minuten),
   4. ruft `pnputil /enable-device "<Instanz-ID>"` auf und beendet sich.
4. Der Benutzer startet das Spiel ganz normal über Steam. Das Spiel selbst läuft **nicht** erhöht.
5. Das Overlay bzw. Tray zeigt den Spielmodus als aktiv an („NVIDIA deaktiviert bis Spielende“) und bietet „Jetzt wieder aktivieren“ an.

### Sicherheitsregeln (werden in AGENTS.md aufgenommen)

| Regel | Umsetzung |
|---|---|
| Nur auf ausdrückliche Benutzeraktion | Kein Automatismus; jede Sitzung: Klick + Bestätigung + UAC |
| Nie die anzeigende GPU | Ablehnen, wenn an der GPU ein Monitor hängt (DXGI-Outputs) oder es die letzte physische GPU wäre |
| Nie `/force` | Fest im Code, Test sichert das ab |
| Keine laufende Arbeit abschießen | Vorher Prozesse mit Speicher/Last auf der GPU anzeigen (PDH); bei aktiver Compute-Last (z. B. Blender-Render) sperren |
| Immer wiederherstellen | Re-Aktivierung bei Spielende, bei Ablauf der Startfrist, über Tray, beim Beenden von SetWhichGPU; nach Absturz/Neustart: Zustand aus der Datenbank → Hinweis „NVIDIA ist noch deaktiviert – jetzt aktivieren?“ |
| Nachvollziehbar | Jede Deaktivierung/Aktivierung im Änderungsprotokoll (Gerät, Grund, Profil, Ergebnis, pnputil-Exitcode) |
| Minimaler erhöhter Code | Der Hilfsprozess akzeptiert nur eine Instanz-ID, die SetWhichGPU als GPU erkannt hat, und einen Prozessnamen; keine freien Befehle |
| Neustart-Fall | Meldet `pnputil` „Neustart erforderlich“ (Gerät belegt), wird der Vorgang abgebrochen und das Gerät sofort wieder aktiviert |

### Nicht Teil dieser Entscheidung

- Treiber deinstallieren/ändern, Geräte entfernen (`/remove-device`), Treiberprofile – bleiben verboten.
- Dauerhaftes Deaktivieren ohne Sitzungsbezug.
- Automatischer Start des Spiels durch SetWhichGPU (ggf. später über Launch-Profile, Phase 4).

## Konsequenzen

- AGENTS.md §4 bekommt eine eng umrissene Ausnahme: „Spielmodus darf eine nicht anzeigende GPU über `pnputil` (ohne `/force`) sitzungsbezogen deaktivieren – nur nach Bestätigung und UAC, immer mit Wiederherstellung.“
- SetWhichGPU selbst läuft weiterhin **nicht** erhöht; nur der Hilfsprozess läuft kurzzeitig mit Admin-Rechten.
- Zwei Nachteile bleiben: eine UAC-Abfrage pro Sitzung und keine NVIDIA-Nutzung (Blender, CUDA, NVIDIA-Overlay) während des Spielens.
- Risiko: Ein Absturz des Hilfsprozesses lässt die RTX deaktiviert → durch die Wiederherstellung beim nächsten Start abgedeckt; im schlimmsten Fall reaktiviert der Benutzer sie im Geräte-Manager.
