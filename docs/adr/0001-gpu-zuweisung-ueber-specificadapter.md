# ADR-0001: GPU-Zuweisung immer über „Bestimmte GPU“ (`SpecificAdapter`)

Status: **angenommen** · 2026-11-18 · Kontext: Phase 3, offene Frage aus [Spike S1](../spikes/S1_specific_gpu.md)

## Kontext

Windows kennt zwei Arten, eine GPU pro Anwendung festzulegen:

1. Präferenzklassen `GpuPreference=1` (Energiesparen) und `=2` (Hohe Leistung). Das Format ist öffentlich bekannt. Welche GPU dahintersteht, entscheidet Windows anhand seiner Einstufung (auf dem Zielsystem: Hoch = Arc, Sparen = AMD).
2. `SpecificAdapter=VEN&DEV&SUBSYS;GpuPreference=1073741824;`. Das Format ist undokumentiert, wird aber von der Einstellungen-App genau so geschrieben, wenn man dort eine bestimmte GPU auswählt. In S1 wurde es für alle drei GPUs verifiziert.

## Entscheidung

Wählt der Benutzer im Overlay eine konkrete GPU, schreibt SetWhichGPU **immer** `SpecificAdapter`, auch dann, wenn eine Klasse zufällig dieselbe GPU liefern würde. „Windows-Standard“ entfernt unsere beiden Felder; sonstige Felder (z. B. `AutoHDREnable`) bleiben erhalten.

## Begründung

- Der Eintrag bildet die Wahl des Benutzers exakt ab. Ändert sich Windows' Einstufung der Hochleistungs-GPU (z. B. über die globale Standard-GPU), bleibt die Zuweisung trotzdem korrekt.
- Es ist dieselbe Darstellung, die Windows selbst für „bestimmte GPU“ verwendet. Ein Wechsel zwischen Overlay und Einstellungen-App ist damit konsistent.
- Für die NVIDIA RTX 3060 gibt es auf dem Zielsystem keinen anderen Weg.

## Konsequenzen

- Abhängigkeit von einem undokumentierten Format. Gegenmaßnahmen: Die Wirkung wird nach dem Neustart der App gemessen („GPU-Präferenz aktiv“ bzw. „nutzt trotz Präferenz eine andere GPU“), und verwaiste Einträge (GPU nicht vorhanden) werden angezeigt.
- Baugleiche GPUs sind nicht unterscheidbar; die Auswahl wird dann deaktiviert.
- Bestehende Klassen-Einträge (z. B. Unity `GpuPreference=2`) werden weiter korrekt gelesen und angezeigt; sie werden erst bei einer bewussten Änderung durch den Benutzer ersetzt.
- Offen (Phase 4): automatischer Selbsttest nach Windows-Updates mit einer Test-EXE.
