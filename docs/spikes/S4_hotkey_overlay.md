# Spike S4 – Globaler Hotkey und Overlay unter Realbedingungen

Status: **erfolgreich** · 2026-11-17 · Prototyp: [tools/spikes/s4_hotkey_overlay.py](../../tools/spikes/s4_hotkey_overlay.py)

Aufbau: PySide6, `RegisterHotKey(Strg+Alt+G, MOD_NOREPEAT)` auf einem versteckten QWidget, `QAbstractNativeEventFilter` für `WM_HOTKEY`, rahmenloses Topmost-Tool-Window mit transparentem Hintergrund.

Monitore: GS34WQC (3440×1440, 150 %, `\\.\DISPLAY2`, Hauptmonitor) und VG2437 (1920×1080, 100 %, `\\.\DISPLAY1`, Ursprung 3440,193).

## Ergebnisse (manueller Test durch den Benutzer + Protokoll)

| Szenario | Hotkey | Ziel erkannt | Overlay-Monitor | Anzeige nach | Fokus zurück |
|---|---|---|---|---|---|
| Unity Editor (DX12) auf GS34WQC | ✔ | `Unity.exe`, PID, Projekttitel | GS34WQC ✔ | 32 ms (erstes Mal) | ✔ |
| Unity-Fenster auf VG2437 | ✔ | ✔ | VG2437 ✔ (DPR 1,0) | 9 ms | ✔ |
| PowerShell **als Administrator** | ✔ | `powershell.exe`, Pfad lesbar | ✔ | 9 ms | **✘** (UIPI) |
| Steam Big Picture (randloses Vollbild, `QUNS_BUSY`) | ✔ | `steamwebhelper.exe` | ✔ | 7 ms | ✔ |
| AltGr+G in VS Code | **löst aus** | ✔ | ✔ | 6 ms | ✔ |

## Erkenntnisse

1. **Reaktionszeit** 6–32 ms vom Hotkey bis zur Anzeige → weit unter dem Ziel von 100 ms. Python/PySide6 ist hier kein Engpass.
2. **Monitorzuordnung:** `QScreen.name()` liefert den Modellnamen („GS34WQC“), nicht `\\.\DISPLAYn`. Die Zuordnung erfolgt über den **physischen Monitorursprung** (`GetMonitorInfoW.rcMonitor` ↔ `QScreen.geometry().topLeft()`; Qt 6 behält den nativen Ursprung). Funktioniert mit gemischter DPI.
3. **Erhöhte Fenster:** Hotkey und Prozesserkennung funktionieren. `SetForegroundWindow` zurück auf das erhöhte Fenster wird jedoch von UIPI verweigert → nach dem Schließen den Fokus nicht erzwingen. Akzeptabel, ggf. Hinweis „Klicke in das Fenster, um fortzufahren“. Eine Admin-Instanz bauen wir dafür **nicht**.
4. **Vollbild:** Randlose Vollbild-Apps (`QUNS_BUSY`) lassen sich überlagern. Exklusives Vollbild (`QUNS_RUNNING_D3D_FULL_SCREEN`) wurde nicht getestet; die geplante Behandlung bleibt: Tray-Benachrichtigung statt Overlay.
5. **AltGr+G löst den Hotkey aus** (Windows meldet AltGr als Strg+Alt). Auf dem deutschen Layout erzeugt AltGr+G kein Zeichen → kein praktischer Konflikt. **Entscheidung D5:** Standard `Strg+Alt+G` bleibt. Die Einstellungen weisen darauf hin, dass AltGr-Kombinationen mit Zeichen (Q, E, 7–0, ß, +, <, M) als Hotkey vermieden werden sollten.
6. Schließen bei Fokusverlust funktioniert. Eine Sperrzeit von 300 ms nach dem Einblenden verhindert sofortiges Schließen.
