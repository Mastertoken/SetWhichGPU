# GPU Control Center – Phase 1: Machbarkeit & Architektur

Status: **Entwurf zur Freigabe** · Stand: 2026-11-17 · Zielsystem: Windows 11 26H2 (Build 26300)

Dieses Dokument enthält die sieben Lieferobjekte aus Phase 1. Aussagen sind markiert:

- **[verifiziert]** – auf dem Zielrechner beobachtet oder durch offizielle Doku gesichert
- **[zu validieren]** – plausibel, aber vor der Implementierung durch einen Spike zu prüfen
- **[undokumentiert]** – funktioniert nur über beobachtetes Windows-/Treiberverhalten, kann sich mit Updates ändern

---

## 0. Zusammenfassung

1. **Machbar:** Tray-App, globaler Hotkey, Overlay über normalen und randlosen Vollbildfenstern, Erkennung der aktiven Anwendung, GPU-Erkennung mit stabilen IDs, Live-Monitoring (Auslastung/VRAM pro GPU *und pro Prozess*), persistente Profile und das Setzen der Windows-Grafikpräferenz pro EXE – alles **ohne Administratorrechte**.
2. **Nur eingeschränkt machbar:** das gezielte Festlegen *einer bestimmten* GPU (z. B. „RTX 3060“ statt „Hohe Leistung“) über die Windows-Präferenz. Windows bietet die Option an (`SpecificGPUOptionApplicable = 1` [verifiziert]), aber das Registry-Format ist **[undokumentiert]**. Das ist Spike S1 und das größte fachliche Risiko.
3. **Nicht machbar (Nicht-Ziel):** GPU-Wechsel laufender Prozesse, Overlay über exklusivem Vollbild, erzwungene Geräteauswahl für CUDA/OptiX/OpenVINO/oneAPI in fremden Anwendungen ohne deren Mitwirkung. Hier liefert die App **Anleitungen, Startprofile (Launcher mit Umgebungsvariablen) und Statusanzeigen**, aber keine Zwangszuweisung.
4. **Technologie:** Python + PySide6 + Win32 (ctypes) ist für dieses Produkt **langfristig geeignet**, solange die Windows-spezifischen Teile hinter klaren Schnittstellen liegen. Ein nativer Helfer wird nur benötigt, falls Spike S2 (DXGI/D3DKMT über ctypes) unzuverlässig ist.

---

## 1. Technische Machbarkeitsanalyse

### 1.1 Befund auf dem Zielrechner [verifiziert]

| Gerät | PnP-Kennung (gekürzt) | Treiber | Bemerkung |
|---|---|---|---|
| Intel Arc Pro B65 | `PCI\VEN_8086&DEV_E222&SUBSYS_60271849&REV_00` | 32.0.101.8976 | trägt beide Monitore |
| NVIDIA GeForce RTX 3060 | `PCI\VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1` | 32.0.16.2124 | PCI-Bus 06:00.0, NVML verfügbar (Temp/Power/Util lesbar) |
| AMD Radeon Graphics (iGPU) | `PCI\VEN_1002&DEV_13C0&SUBSYS_364E1849&REV_C9` | 32.0.21042.62 | Shared Memory |
| Meta Virtual Monitor | `ROOT\DISPLAY\0000` | – | **virtuelles Display, keine GPU** → herausfiltern |

Weitere Beobachtungen:

- `Win32_VideoController.AdapterRAM` meldet für Arc **und** RTX 3060 je ~4 GB – ein bekannter 32-Bit-Überlauf. **WMI ist für VRAM unbrauchbar**; VRAM kommt aus DXGI (`DedicatedVideoMemory`), NVML bzw. Registry (`HardwareInformation.qwMemorySize`).
- `HKCU\Software\Microsoft\DirectX\UserGpuPreferences` enthält bereits `Unity.exe → GpuPreference=2;` („Hohe Leistung“), und Unity rendert auf der Arc. Windows stuft auf diesem System also die **Arc als „Hochleistungs-GPU“** ein. Die RTX 3060 ist über die Klassen „Energiesparen/Hohe Leistung“ daher *nicht* erreichbar – nur über „Bestimmte GPU“.
- `HKCU\Software\Microsoft\DirectX\GraphicsSettings`: `DefaultHighPerfGPUApplicable = 1`, `SpecificGPUOptionApplicable = 1` → die Einstellungen-App erlaubt eine Standard-Hochleistungs-GPU und eine GPU-Auswahl pro App.
- Performance-Counter-Sets vorhanden: `GPU Engine`, `GPU Adapter Memory`, `GPU Local Adapter Memory`, `GPU Non Local Adapter Memory`, `GPU Process Memory`.
- **Python ist nicht installiert** (nur der Microsoft-Store-Alias), **Git wurde nicht gefunden**. Beides ist Voraussetzung für Phase 2 bzw. die Worktree-Zusammenarbeit.

### 1.2 Machbarkeit je Funktion

| Funktion | Bewertung | Mechanismus | Wirksamkeit |
|---|---|---|---|
| Hintergrundbetrieb + Tray | ✅ sicher | `QSystemTrayIcon` | – |
| Autostart (optional) | ✅ sicher | `HKCU\...\CurrentVersion\Run` (kein Admin) | – |
| Globaler Hotkey | ✅ sicher | `RegisterHotKey` | sofort |
| Aktive Anwendung erkennen | ✅ sicher | `GetForegroundWindow` → PID → `QueryFullProcessImageNameW` | – |
| UWP-/Store-Apps erkennen | ✅ mit Sonderfall | `ApplicationFrameHost.exe` → Kindfenster `Windows.UI.Core.CoreWindow` → echte PID | – |
| Erhöhte (Admin-)Prozesse erkennen | ✅ meist | `PROCESS_QUERY_LIMITED_INFORMATION` reicht für Pfad; geschützte Prozesse (PPL) nicht | – |
| Overlay über Fenstern/randlosem Vollbild | ✅ | Topmost-Tool-Window | sofort |
| Overlay über **exklusivem** Vollbild | ❌ Nicht-Ziel | bräuchte Injection/Hooking in Present | – |
| GPUs erkennen, stabile IDs | ✅ | SetupAPI/CfgMgr32 + DXGI (+ NVML) | – |
| GPU-Auslastung, VRAM pro GPU | ✅ alle Hersteller | PDH `GPU Engine`/`GPU Adapter Memory` | live |
| Auslastung/VRAM **pro Prozess und GPU** | ✅ | PDH-Instanzen `pid_X_luid_..._engtype_3D` | live |
| Temperatur/Leistung NVIDIA | ✅ | NVML | live |
| Temperatur/Leistung Intel Arc | ✅ [verifiziert S3] | Intel IGCL (`ControlLib.dll`, kommt mit dem Treiber) | live |
| Temperatur/Leistung AMD iGPU | ⚠️ [zu validieren] | AMD ADLX (C++-API), sonst „nicht verfügbar“ | live |
| Präferenz-Klasse setzen (Auto/Sparen/Hoch) | ✅ dokumentiertes Verhalten, Registry-Format öffentlich bekannt | `UserGpuPreferences` (HKCU) | **ab nächstem Start** |
| **Bestimmte GPU** pro App setzen | ✅ [undokumentiert, verifiziert in S1] | `SpecificAdapter=VEN&DEV&SUBSYS;GpuPreference=1073741824;` | ab nächstem Start |
| Tatsächlich genutzte GPU prüfen | ✅ heuristisch gut | PDH 3D-Engine-Zeit + Prozess-VRAM je LUID | live |
| CUDA/OptiX-Gerät festlegen | ⚠️ nur per Start | `CUDA_VISIBLE_DEVICES` (über Launcher) oder App-Einstellung | ab Start über Launcher |
| oneAPI/OpenVINO-Gerät festlegen | ⚠️ nur per Start/App | `ONEAPI_DEVICE_SELECTOR`, OpenVINO-Device-String in der App | ab Start über Launcher |
| GPU-Wechsel laufender Prozesse | ❌ Nicht-Ziel | Windows bietet das nicht an | – |

### 1.3 Was eine „GPU-Präferenz“ unter Windows tatsächlich bewirkt

- Die Präferenz beeinflusst, **welchen Adapter DXGI einer Anwendung als ersten/Standard-Adapter liefert** (`EnumAdapters`, `EnumAdapterByGpuPreference`, `D3D11/12CreateDevice(nullptr, …)`).
- Sie wird **beim Prozessstart/bei der Device-Erstellung** gelesen. Laufende Prozesse sind nicht betroffen → UI zeigt immer „Wirksam nach Neustart der Anwendung“.
- Anwendungen, die **selbst Adapter auswählen** (Blender Cycles, viele Engines, CUDA-Programme, KI-Frameworks), ignorieren die Präferenz ganz oder teilweise.
- Vulkan: Der Windows-Vulkan-Loader sortiert physische Geräte nach der DXGI-Präferenz [zu validieren pro Loader-Version]; Apps können trotzdem anders wählen.
- OpenGL: Verhalten hängt vom ICD/Treiber ab [zu validieren] – UI kennzeichnet OpenGL-Apps als „Präferenz möglicherweise unwirksam“.
- Display an der Arc: Rendert eine App auf der NVIDIA, wird das Bild per Cross-Adapter-Copy zur Arc kopiert. Das funktioniert, kostet aber etwas Latenz/Bandbreite, und die App erscheint mit geringer Last auch auf der Arc. Die „Rendering-GPU“-Heuristik muss das berücksichtigen (s. 3.5).

---

## 2. Windows- und GPU-APIs mit Einschränkungen

| # | API | Zweck | Zugang aus Python | Admin? | Einschränkungen / Risiken |
|---|---|---|---|---|---|
| A1 | `RegisterHotKey` / `WM_HOTKEY` | globaler Hotkey | ctypes + `QAbstractNativeEventFilter` | nein | Kollision mit anderen Tools (Rückgabe `FALSE` → UI meldet Konflikt). **Strg+Alt = AltGr** auf deutschem Layout → AltGr+G kann auslösen. |
| A2 | `GetForegroundWindow`, `GetWindowThreadProcessId`, `GetWindowTextW` | aktive Anwendung | ctypes | nein | Liefert nach Hotkey noch das Zielfenster, **solange das Overlay vorher nicht aktiviert wurde** → Ziel zuerst erfassen, dann Overlay zeigen. |
| A3 | `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `QueryFullProcessImageNameW` | EXE-Pfad | ctypes / psutil | nein | Geschützte Prozesse (PPL, Anti-Cheat) verweigern Zugriff → „Prozess geschützt“. |
| A4 | `GetFileVersionInfoW` | Produktname/Hersteller der EXE | ctypes / pywin32 | nein | – |
| A5 | `SHQueryUserNotificationState` | exklusives Vollbild erkennen (`QUNS_RUNNING_D3D_FULL_SCREEN`) | ctypes | nein | Nur Indiz. Bei Vollbild: Tray-Benachrichtigung statt Overlay. |
| A6 | `MonitorFromWindow`, `GetDpiForWindow` | Zielmonitor, DPI | ctypes; Qt 6 ist per-monitor-DPI-aware v2 | nein | Qt übernimmt DPI-Skalierung; nur die Monitorauswahl selbst ist eigene Logik. |
| A7 | `DwmSetWindowAttribute` (`DWMWA_SYSTEMBACKDROP_TYPE`, `DWMWA_WINDOW_CORNER_PREFERENCE`) | Acrylic/Mica, runde Ecken | ctypes | nein | Optisch, optional; Fallback auf halbtransparenten Qt-Hintergrund. |
| B1 | **DXGI** `CreateDXGIFactory1` → `IDXGIFactory6::EnumAdapterByGpuPreference`, `IDXGIAdapter1::GetDesc1` | Adapterliste, **LUID**, Vendor/Device/SubSys/Revision, VRAM, Reihenfolge je Präferenz | `comtypes` oder handgeschriebene vtable-Aufrufe per ctypes | nein | COM über ctypes ist fehleranfällig → kapseln, testen; ggf. nativer Helfer (s. 3.8). LUID ändert sich bei jedem Boot/Treiberneustart. |
| B2 | **D3DKMT** (`D3DKMTEnumAdapters2`, `D3DKMTQueryAdapterInfo` mit `KMTQAITYPE_ADAPTERADDRESS`) | LUID ↔ PCI-Bus/Device/Function | ctypes (`gdi32.dll`) | nein | Funktionen in WDK-Headern dokumentiert, für User-Mode aber „Thunks“ – stabil seit Jahren (System Informer/Task-Manager-Klone nutzen sie). Nur lesend. |
| B3 | **SetupAPI/CfgMgr32** (`SetupDiGetClassDevs(GUID_DEVCLASS_DISPLAY)`, `DEVPKEY_Device_LocationInfo`, `DEVPKEY_Device_InstanceId`, Treiberversion/-datum) | stabile Hardware-IDs, Treiberinfo | ctypes | nein | Virtuelle Adapter (ROOT\…) und „Microsoft Basic Display“ filtern. |
| B4 | Registry `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-…}\00xx\HardwareInformation.qwMemorySize` | VRAM-Gegenprobe | winreg | nein (lesen) | Nur lesend. |
| C1 | **PDH** (`PdhAddEnglishCounterW`, `PdhGetFormattedCounterArrayW`) auf `\GPU Engine(*)\Utilization Percentage`, `\GPU Adapter Memory(*)\Dedicated Usage`, `\GPU Process Memory(*)\…` | herstellerneutrales Monitoring, pro Prozess und Engine | ctypes (oder pywin32 `win32pdh`) | nein | Instanznamen enthalten PID + LUID + Engine-Typ. Wildcard-Abfragen kosten bei vielen Prozessen spürbar CPU → Intervall adaptiv, nur bei sichtbarem Overlay 1 s. **Kein WMI** (zu langsam/schwer). Werte sind Task-Manager-Logik, keine Treiber-Wahrheit. |
| D1 | **NVML** (`nvidia-ml-py`, offizielles Paket) | Temp, Power, Util, VRAM, PCI-Bus-ID, UUID | Python-Binding, `nvml.dll` im System | nein | Unter WDDM liefern `nvmlDeviceGetComputeRunningProcesses`/`…GraphicsRunningProcesses` oft **keinen** Prozess-VRAM (`NOT_AVAILABLE`) → Prozessdaten aus PDH. NVML-Indizes ≠ CUDA-Indizes ≠ DXGI-Reihenfolge → Zuordnung **nur über PCI-Bus-ID**. |
| D2 | NVAPI DRS (Treiberprofile, „CUDA – GPUs“, „OpenGL-Rendering-GPU“) | NVIDIA-seitige App-Profile | C-API | nein | Ändert **Treiberprofile** → widerspricht „keine Treibermanipulation“. **Nicht-Ziel** (höchstens später, lesend). |
| E1 | **Intel IGCL** (`ControlLib.dll`, `ctlInit`, `ctlEnumerateDevices`, `ctlPowerTelemetryGet`) | Temp, Power, Frequenz, VRAM-Nutzung der Arc | ctypes gegen C-API (Header aus `intel/drivers.gpu.control-library`) | nein [zu validieren] | Strukturen versioniert; Unterstützung der B65 und einzelner Felder ist zu prüfen (Spike S3). Fallback: nur PDH. |
| E2 | Intel Level Zero Sysman (`ze_loader.dll`, `zes*`) | Alternative zu IGCL | ctypes | ? | Windows-Unterstützung von Sysman ist lückenhaft → nur zweite Wahl. |
| F1 | **AMD ADLX** | Telemetrie der Radeon iGPU | C++-Interfaces, offizielle Python-Bindings als Beispiel im SDK | nein | Aufwand hoch, Nutzen gering (iGPU ohne Monitor). **Phase 4**, Fallback PDH. |
| G1 | `UserGpuPreferences` (HKCU) | Windows-Grafikpräferenz pro EXE | winreg | **nein** | Format `GpuPreference=0|1|2;` ist öffentlich bekannt, aber nicht formal als API dokumentiert; Key = voller EXE-Pfad (Pfadwechsel bei App-Updates, z. B. Unity-Versionsordner!). Weitere Felder im selben String (z. B. `AutoHDREnable`, `SwapEffectUpgradeEnable`) **müssen erhalten bleiben**. |
| G2 | „Bestimmte GPU“ pro App / globale Standard-Hochleistungs-GPU (`DirectXUserGlobalSettings`, beobachtet z. B. `HighPerfAdapter=VEN&DEV&SUBSYS`) | gezielte GPU-Wahl | winreg | nein | **[undokumentiert]**. Format wird in Spike S1 durch Setzen in der Einstellungen-App und Auslesen ermittelt. Die globale Einstellung wird von uns **nie** ungefragt verändert. |
| H1 | `CUDA_VISIBLE_DEVICES`, `CUDA_DEVICE_ORDER=PCI_BUS_ID` | CUDA-Geräteauswahl | Umgebungsvariable beim Start | nein | Wirkt nur für Prozesse, die **über unseren Launcher** gestartet werden. Systemweit setzen wäre eine globale Systemänderung → nur auf ausdrücklichen Wunsch, per Benutzer-Umgebung. |
| H2 | `ONEAPI_DEVICE_SELECTOR` (z. B. `level_zero:gpu`), OpenVINO `GPU.0/GPU.1` | Intel-Compute | Umgebungsvariable / App-Konfiguration | nein | OpenVINO-Gerät wählt die App im Code/Config → nur Hinweis + Launcher-Profil. |
| H3 | App-spezifisch: Blender (`--python-expr` zum Setzen von `preferences.addons['cycles'].preferences.compute_device_type='OPTIX'` und Gerätefilter), Premiere Pro (Mercury Playback Engine, Projekteinstellung) | Compute-Gerät in der App | Launcher-Argumente bzw. Anleitung | nein | Pro App eigener „Connector“ (Phase 4). Premiere: nur Anzeige der unterstützten Optionen + Anleitung, **keine** Manipulation von Adobe-Dateien in v1. |

---

## 3. Architekturkonzept

### 3.1 Leitprinzipien

1. **Ports & Adapters:** Fachlogik (`core`) kennt keine Win32-/NVML-Details. Jede Plattformquelle implementiert ein Protokoll (`typing.Protocol`). Dadurch sind Kernlogik und UI ohne Windows-GPU testbar.
2. **Ehrliche Fähigkeiten:** Jede Zuweisungsart meldet ein `SupportLevel` und einen `Effect` (sofort / nach App-Neustart / nur über Launcher / nicht unterstützt). Die UI zeigt nie mehr, als das Backend garantiert.
3. **Präferenz ≠ Beobachtung:** `PreferredGpu` (gespeichert) und `ObservedGpu` (gemessen) sind getrennte Typen, die nie vermischt werden.
4. **Stabile Identität:** `GpuKey` aus PCI-Kennung + Bus-Ort, nie ein Index. LUIDs und NVML-Indizes sind nur Laufzeit-Zuordnungen.
5. **Minimale Eingriffe:** Schreibzugriffe nur auf HKCU, nur auf Werte, die der Benutzer im UI bestätigt hat, immer mit Journal-Eintrag (vorher/nachher) und Wiederherstellbarkeit.
6. **Sparsam:** Monitoring läuft nur in voller Frequenz, wenn das Overlay sichtbar ist.

### 3.2 Prozess- und Thread-Modell

```
gpucc.exe (ein Prozess, nicht erhöht)
├─ Qt-Hauptthread
│   ├─ TrayService (QSystemTrayIcon, Menü)
│   ├─ HotkeyService (verstecktes Nachrichtenfenster + NativeEventFilter für WM_HOTKEY)
│   ├─ OverlayWindow (rahmenlos, topmost, Tool-Window, ein Exemplar, wiederverwendet)
│   └─ Controller/ViewModels (Qt-Signale)
├─ MonitoringWorker (QThread)
│   └─ Sampler: PDH + NVML + IGCL  →  Snapshot (immutable dataclass) → Signal an UI
└─ (Phase 5) LocalApiServer (asyncio in eigenem Thread, 127.0.0.1 / Named Pipe)

gpucc-mcp.exe (Phase 5, separater Prozess) ──► spricht nur mit LocalApiServer
```

Einzelinstanz-Garantie über benanntes Mutex (`Local\GpuControlCenter.Singleton`); ein zweiter Start bringt das Overlay der laufenden Instanz nach vorn.

### 3.3 Module

| Modul | Verantwortung | Wichtige Typen / Schnittstellen |
|---|---|---|
| `discovery` | Adapter aufzählen, virtuelle filtern, IDs zusammenführen (SetupAPI + DXGI + D3DKMT + NVML), Fähigkeiten (D3D12, CUDA, Level Zero, OptiX) ableiten | `GpuKey`, `GpuInfo`, `GpuCapabilities`, `DiscoveryService.scan() -> list[GpuInfo]` |
| `monitoring` | periodische Snapshots: Util je Engine, VRAM, Temp, Power, Prozesszuordnung | `TelemetrySource` (Protocol), `PdhSource`, `NvmlSource`, `IgclSource`, `AdlxSource`, `GpuSnapshot`, `ProcessGpuUsage` |
| `appdetect` | Zielfenster erfassen, PID/EXE/Produktname, UWP-Auflösung, Vollbild-/Schutzstatus | `TargetApp`, `ForegroundProbe.capture() -> TargetApp` |
| `assignment` | Präferenzen anwenden/lesen/zurücksetzen über austauschbare Backends | `AssignmentBackend` (Protocol) mit `supports(app, gpu) -> Support`, `read()`, `apply()`, `revert()`; Backends: `WindowsGpuPreference`, `WindowsSpecificAdapter` (hinter Feature-Flag bis S1 grün), `LaunchEnvironment` (CUDA/oneAPI), `AppConnector` (Blender …) |
| `profiles` | Profile, Regeln, Matching (Pfad, Glob, Publisher, Produktname), Import/Export, Backups | `Profile`, `Rule`, `ProfileRepository` (SQLite), `RuleEngine` |
| `ui.overlay` | Overlay, Tastaturbedienung, Darstellung Präferenz vs. Beobachtung | `OverlayWindow`, `OverlayViewModel` |
| `ui.tray` | Tray-Icon, Menü, Einstellungen, Autostart | `TrayService`, `SettingsDialog` |
| `platform.win32` | **einzige** Stelle mit ctypes-Deklarationen | `user32`, `kernel32`, `pdh`, `dxgi`, `d3dkmt`, `setupapi`, `registry` |
| `diagnostics` | strukturiertes Logging, Diagnosebericht (ZIP), Selbsttest | `configure_logging()`, `DiagnosticsReport` |
| `api` (Phase 5) | lokale API, Auth-Token, Freigabe-Workflow | `LocalApiServer`, `ApprovalQueue` |

### 3.4 GPU-Identität

```
GpuKey  = "PCI:VEN_10DE&DEV_2504&SUBSYS_881D1043&REV_A1@0006:00.0"
          └─ PnP-Hardware-ID ─────────────────────┘ └─ PCI-Ort (Bus:Dev.Fn) ┘
```

- Der PCI-Ort trennt identische Karten; Vendor/Device/SubSys machen den Schlüssel nach Steckplatzwechsel wiedererkennbar (Fallback-Matching ohne Ort mit Benutzerbestätigung).
- Laufzeit-Bindungen pro Scan: `GpuKey → LUID (DXGI/D3DKMT)`, `GpuKey → NVML-Handle (über PCI-Bus-ID)`, `GpuKey → IGCL-Device (über PCI-Adresse)`, `GpuKey → CUDA-Ordinal` (nur gültig mit `CUDA_DEVICE_ORDER=PCI_BUS_ID`).
- Rescan bei `WM_DEVICECHANGE` / `WM_DISPLAYCHANGE` und nach Standby (LUIDs können sich ändern).

### 3.5 Bestimmung der tatsächlich genutzten GPU

Für die Ziel-PID (inkl. Kindprozesse, z. B. Unity-Worker, Chrome-GPU-Prozess) aus PDH:

1. Summe der `engtype_3D`- und `engtype_Compute*`-Zeit je LUID über ein Fenster von 2–3 Samples.
2. Dedizierter Prozess-VRAM je LUID.
3. Die `Copy`-Engine und kleine Last auf dem Display-Adapter (Arc) werden als „Präsentation“ gewertet, nicht als Rendering.

Ergebnis mit Konfidenz: `ObservedGpu(gpu, confidence: high|medium|low|idle)`. Im Leerlauf dient die VRAM-Residenz als zweites Signal (`medium`), siehe [S5/S6](../spikes/S5_S6_pdh_attribution.md). Bei Leerlauf zeigt die UI „keine aktive GPU-Last – Zuordnung nicht bestimmbar“ statt zu raten.

### 3.6 Zuweisungsmodell

```python
class Effect(Enum):
    NEXT_APP_START = auto()  # Windows-Präferenz
    LAUNCHER_ONLY = auto()  # Umgebungsvariablen, App-Argumente
    MANUAL_IN_APP = auto()  # nur Anleitung (z. B. Premiere)
    UNSUPPORTED = auto()


@dataclass(frozen=True)
class Support:
    level: Literal["supported", "experimental", "unsupported"]
    effect: Effect
    reason: str  # wird in der UI angezeigt
```

Ablauf „GPU wählen“ im Overlay:

1. `RuleEngine` liefert das passende Profil (oder legt eines für die EXE an).
2. Jedes Backend meldet `supports(app, gpu)`. Die UI zeigt alle Optionen; nicht unterstützte sind sichtbar, aber deaktiviert, mit Begründung.
3. `apply()` schreibt die Änderung, `ChangeJournal` speichert den alten und neuen Registry-String.
4. Läuft die App, steht in der UI: „Gespeichert – wirksam nach Neustart von Unity“. Nach dem Neustart vergleicht `ObservedGpu` das Ergebnis und markiert das Profil mit „bestätigt“ oder „Präferenz wird von der App ignoriert“.

Zuordnung der Auswahl auf Windows-Werte (vorläufig, wird durch S1 bestätigt):

| Auswahl | Mechanismus |
|---|---|
| Windows-Standard | Wert entfernen bzw. `GpuPreference=0;` (sonstige Felder erhalten) |
| AMD iGPU | `GpuPreference=1;` (Energiesparen) – **nur wenn** DXGI-Reihenfolge `MINIMUM_POWER` die iGPU liefert |
| Intel Arc | `GpuPreference=2;` – **nur wenn** DXGI-Reihenfolge `HIGH_PERFORMANCE` die Arc liefert (aktuell der Fall) |
| NVIDIA RTX 3060 | `SpecificAdapter=10DE&2504&881D1043;GpuPreference=1073741824;` – Format durch S1 ermittelt und verifiziert ([S1](../spikes/S1_specific_gpu.md)), Status „experimentell“ |

Die Zuordnung wird nicht fest kodiert. Bei jedem Scan prüft das Programm per `EnumAdapterByGpuPreference`, welche GPU Windows für „Sparen“ bzw. „Hoch“ liefert.

### 3.7 Persistenz

- Ort: `%LOCALAPPDATA%\GpuControlCenter\` → `gpucc.db` (SQLite, WAL), `logs\`, `backups\`.
- Tabellen: `schema_version`, `gpus` (bekannte GpuKeys, Anzeigename), `profiles`, `rules`, `settings`, `change_journal` (Zeit, Ziel, alter Wert, neuer Wert, Auslöser UI/API, Ergebnis), `launch_profiles`.
- Migrationen versioniert (einfache SQL-Skripte, kein ORM nötig).
- Export/Import als JSON mit Schema-Version; GPUs werden über `GpuKey` referenziert, beim Import auf anderen Rechnern per Vendor/Device neu zugeordnet.
- **Wiederherstellung:** „Alle von GPU Control Center gesetzten Präferenzen zurücksetzen“ spielt das Journal rückwärts ab. Werte, die der Benutzer zwischenzeitlich außerhalb geändert hat, werden erkannt und nicht überschrieben (Vergleich mit dem zuletzt geschriebenen Wert).

### 3.8 Native Komponenten (nur bei Bedarf)

> **Update nach den Spikes S2/S3:** DXGI, D3DKMT, SetupAPI, PDH und IGCL funktionieren zuverlässig über reines ctypes. Ein nativer Helfer ist **derzeit nicht erforderlich**. Der folgende Abschnitt bleibt als Rückfalloption bestehen.

Falls DXGI/D3DKMT/IGCL über ctypes in Spike S2/S3 instabil oder zu umständlich sind: kleines natives Modul **`gpucc_native`** (C++20, pybind11 oder nanobind, per scikit-build-core gebaut), das ausschließlich **lesende** Funktionen bereitstellt (`enum_adapters()`, `adapter_address(luid)`, `igcl_telemetry()`). Keine UI, kein Schreibzugriff. Zweite Wahl: eigenständige `gpucc-probe.exe` mit JSON-Ausgabe (einfacher zu bauen, aber Prozessstart pro Abfrage).

### 3.9 Sicherheit

- Läuft **nicht erhöht**; keine Funktion benötigt in v1 Admin-Rechte. Funktionen, die Admin brauchen würden, werden nicht gebaut.
- Kein Hooking, keine Injection, kein Zugriff auf fremden Prozessspeicher, keine Treiberprofile.
- Schreibzugriffe ausschließlich: `HKCU\...\DirectX\UserGpuPreferences` (nur bestätigte Einträge), `HKCU\...\Run` (nur bei aktiviertem Autostart), eigenes AppData-Verzeichnis.
- Phase 5: API nur auf Loopback/Named Pipe mit zufälligem Token in einer ACL-geschützten Datei. Lesende Endpunkte frei, schreibende Endpunkte erzeugen eine **Freigabeanfrage**, die im Overlay/Tray bestätigt werden muss (konfigurierbar pro Aktion, Standard: immer bestätigen).

### 3.10 Bewertung: Python + PySide6 + Win32

**Ergebnis: geeignet, mit Auflagen.**

| Kriterium | Bewertung |
|---|---|
| Overlay/Tray/Hotkey | Qt 6 unterstützt rahmenlose, transparente, topmost-Fenster, Per-Monitor-DPI v2 und Native-Event-Filter vollständig. Für ein kleines Panel völlig ausreichend. |
| Reaktionszeit | Overlay bleibt geladen und wird nur ein-/ausgeblendet → < 100 ms bis zur Anzeige [zu validieren in Phase 2]. Der kalte Start (~1–2 s) passiert einmal beim Login. |
| Ressourcen | Erwartet ~70–130 MB RAM und nahe 0 % CPU im Leerlauf (Monitoring ruht, solange das Overlay verborgen ist). Ein C#-/C++-Tray-Tool wäre mit ~20–40 MB sparsamer – für eine Workstation mit 12 + 32 GB VRAM vertretbar. |
| Win32-Zugriff | ctypes deckt user32/kernel32/pdh/advapi32 problemlos ab. COM (DXGI) per ctypes ist der heikelste Teil → kapseln, ggf. nativer Helfer (3.8). |
| GPU-APIs | NVML hat ein offizielles Python-Binding; IGCL und ADLX sind C/C++ → ctypes bzw. nativer Helfer. |
| KI-Integration (Phase 5) | Python ist hier ein Vorteil: offizielles MCP-SDK, einfache lokale API. |
| Distribution | PyInstaller oder Nuitka. Risiko: Virenscanner melden ungesignierte Python-EXEs fälschlich → Code-Signing einplanen. |
| Grenzen | Bei exklusivem Vollbild würde jede Sprache scheitern (bräuchte Injection, Nicht-Ziel). Kein Grund für einen Sprachwechsel. |

Alternative zum Vergleich: C# / .NET 9 mit WinUI 3 oder WPF bietet etwas besseren Win32/COM-Zugriff und einen kleineren Speicherbedarf. Dafür fehlen NVML-/MCP-Bindings in dieser Qualität, und die geplante Python-Codebasis müsste neu entstehen. **Empfehlung: bei Python bleiben** und die Plattformschicht so schneiden, dass ein späterer nativer Austausch einzelner Adapter möglich bleibt.

UI-Technik: **Qt Widgets + QSS** statt QML. Sie sind leichter, starten schneller und lassen sich mit `pytest-qt` einfacher testen. Animationen beschränken sich auf Ein-/Ausblenden (`QPropertyAnimation` auf `windowOpacity`).

---

## 4. Projektstruktur

```
GraphicsCardChooser/
├─ AGENTS.md                     # verbindliche Regeln für Codex CLI und Claude Code
├─ CLAUDE.md                     # verweist auf AGENTS.md
├─ README.md
├─ pyproject.toml                # uv, ruff, mypy, pytest-Konfiguration
├─ uv.lock
├─ docs/
│  ├─ architecture/PHASE1_ARCHITEKTUR.md
│  ├─ adr/                       # Architekturentscheidungen (ADR-0001 …)
│  └─ spikes/                    # Ergebnisse S1–S6
├─ src/gpucc/
│  ├─ __main__.py                # Einstieg: python -m gpucc
│  ├─ app.py                     # Composition Root: verdrahtet Services
│  ├─ core/
│  │  ├─ models.py               # GpuKey, GpuInfo, TargetApp, Snapshot, Support, Effect …
│  │  ├─ ports.py                # Protocols: TelemetrySource, AssignmentBackend, …
│  │  └─ errors.py
│  ├─ discovery/                 # service.py, merge.py (ID-Zusammenführung), filters.py
│  ├─ monitoring/                # sampler.py, attribution.py (ObservedGpu), sources/{pdh,nvml,igcl,adlx}.py
│  ├─ appdetect/                 # foreground.py, uwp.py, fullscreen.py
│  ├─ assignment/                # service.py, backends/{win_pref,win_specific,launch_env,blender}.py
│  ├─ profiles/                  # repository.py, rules.py, migrations/, export.py
│  ├─ platform/win32/            # user32.py, kernel32.py, pdh.py, dxgi.py, d3dkmt.py, setupapi.py, registry.py
│  ├─ ui/
│  │  ├─ overlay/                # window.py, viewmodel.py, widgets/, style.qss
│  │  ├─ tray/                   # service.py, settings_dialog.py
│  │  └─ hotkey.py
│  ├─ diagnostics/               # logging.py, report.py, selftest.py
│  └─ api/                       # Phase 5: server.py, approval.py
├─ native/                       # nur falls benötigt (3.8): gpucc_native (C++)
├─ tests/
│  ├─ unit/                      # ohne Windows-GPU lauffähig, Fakes für alle Ports
│  ├─ integration/               # echtes Windows, Marker @pytest.mark.windows
│  ├─ hardware/                  # nur mit GPUCC_HW_TESTS=1, Marker @pytest.mark.hardware
│  └─ fixtures/                  # aufgezeichnete PDH-/NVML-/Registry-Daten dieses Rechners
└─ tools/                        # Spike-Skripte, Diagnose-Helfer
```

---

## 5. UI-Konzept Overlay

### 5.1 Layout (ca. 440 × 520 logische Pixel, skaliert mit DPI)

```
┌──────────────────────────────────────────────────────┐
│  ◆ Unity Editor                         Strg+Alt+G ✕ │
│    Unity.exe · C:\Program Files\Unity\…\Editor        │
│    PID 18244 · Unity Technologies                     │
├──────────────────────────────────────────────────────┤
│  Rendert auf     ● Intel Arc Pro B65   (hohe Konfid.)│
│  Präferenz       ● Intel Arc Pro B65   ✔ aktiv       │
├──────────────────────────────────────────────────────┤
│  GPU wählen                                           │
│   ( ) Windows-Standard                                │
│   (•) Intel Arc Pro B65        3D 41%  VRAM 9.8/32 GB │
│   ( ) NVIDIA RTX 3060          3D  2%  VRAM 1.1/12 GB │
│        ⚠ experimentell – Format „Bestimmte GPU“       │
│   ( ) AMD Radeon iGPU          3D  0%  shared         │
│                                                       │
│   ℹ Wirksam nach Neustart der Anwendung               │
│   [ Übernehmen ]   [ Compute-Profil … ]               │
├──────────────────────────────────────────────────────┤
│  Arc B65   ▮▮▮▮▯▯▯▯ 41%  9.8/32 GB  63°C  88 W        │
│  RTX 3060  ▮▯▯▯▯▯▯▯  2%  1.1/12 GB  36°C   9 W        │
│  Radeon    ▯▯▯▯▯▯▯▯  0%  —          —      —          │
│  ▸ Prozesse & Engines                                 │
└──────────────────────────────────────────────────────┘
```

### 5.2 Verhalten

- **Öffnen:** Hotkey → Zielfenster erfassen (vor jeder Fokusänderung) → Overlay mittig auf dem **Monitor des Zielfensters** einblenden (150 ms Fade) → Fokus übernehmen (der Hotkey berechtigt zu `SetForegroundWindow`).
- **Schließen:** Esc, gleicher Hotkey, Klick außerhalb (Fokusverlust) → Fokus an das Zielfenster zurückgeben.
- **Tastatur:** ↑/↓ wählt die GPU, Enter übernimmt, Tab wechselt den Bereich, `P` klappt die Prozesse auf. Komplett ohne Maus bedienbar.
- **Statusfarben:** Grün = Präferenz bestätigt, Gelb = gespeichert/Neustart nötig oder App ignoriert die Präferenz, Grau = nicht unterstützt (mit Begründung im Tooltip), Rot = Fehler.
- **Präferenz vs. Beobachtung:** zwei getrennte Zeilen, nie zusammengefasst.
- **Sonderfälle:**
  - Exklusives Vollbild erkannt → kein Overlay, stattdessen Tray-Benachrichtigung „Overlay im exklusiven Vollbild nicht verfügbar“ (Option: trotzdem auf dem zweiten Monitor öffnen).
  - Geschützter Prozess → Name soweit lesbar, Hinweis „Prozess geschützt – nur Präferenz über Pfad möglich“.
  - Desktop/Explorer/Overlay selbst im Fokus → Overlay zeigt die GPU-Übersicht ohne Ziel-App.
  - Erhöhter Zielprozess: Lesen funktioniert, Präferenz (HKCU) funktioniert. Hinweis: wird die App „als Administrator“ unter einem anderen Konto gestartet, gilt dessen HKCU.
- **Optik:** dunkles halbtransparentes Panel (Hintergrund ~88 % Deckkraft), runde Ecken (Win11 `DWMWCP_ROUND`), optional Acrylic über `DWMWA_SYSTEMBACKDROP_TYPE`. Hell/Dunkel folgt dem Systemthema. Kein Taskleisteneintrag (`Qt.Tool`).
- **Tray:** Overlay öffnen · Profile … · Einstellungen (Hotkey, Autostart, Intervalle, Telemetriequellen) · Diagnosebericht exportieren · Präferenzen zurücksetzen … · Beenden.

---

## 6. Priorisierter Implementierungsplan

### Phase 1b – Spikes vor dem MVP (je ≤ ½ Tag, Ergebnis nach `docs/spikes/`)

| ID | Frage | Erfolgskriterium | Priorität |
|---|---|---|---|
| S0 | Werkzeuge einrichten | Python 3.13 (via `uv`), Git, `git init`, Grundgerüst `pyproject.toml` | Blocker |
| S1 | Registry-Format „Bestimmte GPU“ | In der Einstellungen-App für eine Test-EXE nacheinander NVIDIA/Arc/AMD wählen, Registry-Diff dokumentieren, mit `dxdiag`-ähnlichem Testprogramm (DXGI-Standardadapter) bestätigen | **hoch** |
| S2 | DXGI + D3DKMT über ctypes | Liste mit LUID, Ven/Dev/SubSys, VRAM, PCI-Adresse für alle 3 GPUs; Abgleich mit NVML-PCI-Bus-ID | hoch |
| S3 | Intel IGCL über ctypes | Temperatur, Leistung und VRAM der Arc B65 lesbar ohne Admin | mittel |
| S4 | Hotkey + Overlay unter Randbedingungen | Funktioniert über Unity, Blender, erhöhtem Fenster, randlosem Vollbild; AltGr-Verhalten auf DE-Layout | hoch |
| S5 | PDH-Kosten | CPU-Last eines `GPU Engine(*)`-Samples bei ~300 Prozessen; Ziel < 1 % CPU bei 1 s Intervall | mittel |
| S6 | Attribution | Unity (Arc) und Blender Cycles (RTX) werden korrekt als Rendering-/Compute-GPU erkannt | mittel |

### Phase 2 – Overlay-MVP

1. Projektgerüst, Logging, Einzelinstanz, Composition Root, Fakes für alle Ports
2. `discovery` (SetupAPI + DXGI + NVML) inkl. Filter für virtuelle Adapter
3. Tray-Service + Hotkey-Service (konfigurierbar, Konflikterkennung)
4. `appdetect` (inkl. UWP, Vollbild, geschützte Prozesse)
5. Overlay (nur Anzeige): Ziel-App, GPU-Liste, Basis-Metriken
6. `monitoring` mit PDH + NVML, adaptivem Intervall
7. Tests: Unit (Fakes) + Integration (Windows) + aufgezeichnete Fixtures

### Phase 3 – GPU-Präferenzen

1. SQLite-Repository + Migrationen + Change-Journal
2. Backend `WindowsGpuPreference` (Klassen 0/1/2, Feldererhalt, Ermittlung der Zuordnung per DXGI-Reihenfolge)
3. Backend `WindowsSpecificAdapter` hinter Feature-Flag (abhängig von S1)
4. Auswahl im Overlay, Neustart-Hinweis, Bestätigung durch Beobachtung nach Neustart
5. Zurücksetzen/Wiederherstellen, Behandlung von EXE-Pfad-Wechseln (z. B. neue Unity-Version → Vorschlag, das Profil zu übernehmen)

### Phase 4 – Erweitert

Regel-Engine (Glob/Publisher/Produktname), Launch-Profile (CUDA/oneAPI-Umgebung, Startmenü-Verknüpfungen „über GPU Control Center starten“), Blender-Connector, IGCL/ADLX-Telemetrie, Prozessansicht, optionales Dashboard, Export/Import.

### Phase 5 – KI-Integration

Lokale API (lesend zuerst), Freigabe-Workflow, MCP-Server als eigener Prozess (Tools: `list_gpus`, `get_snapshot`, `get_app_gpu`, `list_profiles`, `propose_profile_change` → Freigabe), Audit-Log.

---

## 7. Technische Risiken und offene Entscheidungen

### 7.1 Risiken

| # | Risiko | Wahrsch. | Auswirkung | Gegenmaßnahme |
|---|---|---|---|---|
| R1 | Format „Bestimmte GPU“ ist undokumentiert / ändert sich mit Windows-Updates | mittel | NVIDIA nicht per Windows-Präferenz wählbar | Feature-Flag, Selbsttest nach jedem Windows-Update (Testprogramm prüft den DXGI-Standardadapter), Fallback: Anleitung „in Einstellungen → Grafik setzen“ mit direktem Link `ms-settings:display-advancedgraphics` |
| R2 | Apps ignorieren die Windows-Präferenz (Blender, CUDA, KI-Tools) | hoch | Erwartung des Benutzers verfehlt | Beobachtung nach Neustart + klare Statusanzeige; Launch-Profile/Connectoren |
| R3 | EXE-Pfad ändert sich bei Updates (Unity Hub-Versionen, Squirrel-Apps) | hoch | Präferenz greift nicht mehr | Regeln über Produktname/Publisher, Erkennung neuer Pfade, Vorschlag zum Übernehmen |
| R4 | Hotkey-Konflikt / AltGr-Auslösung auf DE-Layout | mittel | Fehlauslösung oder kein Hotkey | Konflikterkennung, alternativer Standard (z. B. Strg+Umschalt+Alt+G) als Vorschlag |
| R5 | PDH-Abfragen zu teuer bei vielen Prozessen | niedrig–mittel | CPU-Last im Hintergrund | adaptives Intervall, im Hintergrund nur Adapter-Summen, Prozessdetails nur bei offenem Overlay |
| R6 | COM/DXGI über ctypes instabil | mittel | Abstürze, falsche Daten | Kapselung, Tests mit Fixtures, nativer Helfer (3.8) |
| R7 | IGCL unterstützt Arc Pro B65 nicht vollständig | mittel | keine Temperatur/Leistung für Arc | Feld-für-Feld „nicht verfügbar“, PDH als Basis |
| R8 | Virenscanner-Fehlalarm bei gepackter EXE | mittel | Installation blockiert | Code-Signing, Nuitka statt PyInstaller testen |
| R9 | Mehrere Agenten (Codex/Claude) ändern gemeinsame Verträge parallel | mittel | Merge-Konflikte, inkonsistente Modelle | Regeln in AGENTS.md: `core/models.py`/`ports.py` nur über eigene Änderung mit ADR |
| R10 | Meta Virtual Monitor / weitere virtuelle Adapter verwirren Discovery und Attribution | niedrig | falsche Liste | Filter: nur `PCI\`-Enumerator, DXGI-Flag `DXGI_ADAPTER_FLAG_SOFTWARE` ausschließen |

### 7.2 Offene Entscheidungen (benötigen deine Freigabe)

| # | Entscheidung | Empfehlung |
|---|---|---|
| D1 | Python-Version und Paketverwaltung | Python **3.13** über **uv** (Projekt-lokal, kein Store-Python) |
| D2 | Git installieren und Repo initialisieren (Voraussetzung für Worktrees) | ja, per `winget install Git.Git` |
| D3 | Qt Widgets oder QML | **Qt Widgets** |
| D4 | „Bestimmte GPU“ (undokumentiert) überhaupt nutzen? | ja, als **experimentell** markiert, nach S1, mit Selbsttest |
| D5 | Standard-Hotkey wegen AltGr-Kollision | **entschieden (S4):** `Strg+Alt+G` bleibt. AltGr+G löst zwar aus, erzeugt auf DE-Layout aber kein Zeichen |
| D6 | Systemweite Umgebungsvariablen (z. B. `CUDA_DEVICE_ORDER`) setzen dürfen? | **nein**, nur in Launch-Profilen |
| D7 | NVIDIA-Treiberprofile (NVAPI DRS) | **nein** (Nicht-Ziel, widerspricht Sicherheitsvorgaben) |
| D8 | AMD-iGPU-Telemetrie per ADLX | auf Phase 4 verschieben, bis dahin nur PDH |
| D9 | Packaging | Phase 2–3 Start per `uv run`, Packaging (Nuitka/PyInstaller + Signierung) ab Phase 4 |
| D10 | Lizenz / Veröffentlichung | offen – privat oder Open Source? |

### 7.3 Nicht-Ziele

- GPU-Wechsel bereits laufender Prozesse
- Overlay in exklusivem Vollbild, In-Game-Overlays, DLL-Injection, Hooking
- Änderungen an Grafiktreibern, Treiberprofilen (NVAPI DRS, Intel/AMD-Profile), Geräte-Deaktivierung
- Übertaktung, Lüfter- oder Power-Limit-Steuerung
- Systemweite Änderungen ohne ausdrückliche Bestätigung
- Funktionen, die Administratorrechte erfordern
