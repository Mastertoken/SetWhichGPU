"""German translations. Keys are the English source strings used with ``tr()``.

``tests/unit/test_i18n.py`` checks that every ``tr("…")`` in the source has an entry here and that
placeholders match.
"""

CATALOG: dict[str, str] = {
    # --- hotkey modifiers
    "Ctrl": "Strg",
    "Shift": "Umschalt",
    # --- preference kinds
    "Windows default": "Windows-Standard",
    "Power saving": "Energiesparen",
    "High performance": "Hohe Leistung",
    "specific GPU": "bestimmte GPU",
    # --- overlay: values
    "{size} reserved · shared memory": "{size} reserviert · geteilter Speicher",
    "shared memory": "geteilter Speicher",
    "no load": "keine Last",
    "unknown": "unbekannt",
    "GPU overview": "GPU-Übersicht",
    "No application in the foreground": "Keine Anwendung im Vordergrund",
    "No GPU usage detected": "Keine GPU-Nutzung erkennbar",
    "{gpu} · memory in use, currently no load": "{gpu} · Speicher belegt, derzeit keine Last",
    "{gpu} · several GPUs, largest memory share": "{gpu} · mehrere GPUs, größter Speicheranteil",
    "None – Windows decides ({gpu})": "Keine – Windows entscheidet ({gpu})",
    "Unknown entry: {raw}": "Unbekannter Eintrag: {raw}",
    "GPU {token} not present – Windows uses its default": "GPU {token} nicht vorhanden – Windows nutzt Standard",
    "– (not running)": "– (läuft nicht)",
    "Not running – the preference applies on next start": "Läuft nicht – die Präferenz wirkt beim nächsten Start",
    "Not running – no own GPU preference": "Läuft nicht – keine eigene GPU-Präferenz",
    "Program file no longer exists (e.g. old version) – the entry can be reset.": (
        "Programmdatei existiert nicht mehr (z. B. alte Version) – Eintrag kann zurückgesetzt werden."
    ),
    "Application has exited – values show the last known state.": (
        "Anwendung wurde beendet – Werte zeigen nur noch den letzten Stand."
    ),
    "Protected process – path and details not readable.": "Prozess geschützt – Pfad und Details nicht lesbar.",
    "Store app detected (resolved via ApplicationFrameHost).": (
        "Store-App erkannt (über ApplicationFrameHost aufgelöst)."
    ),
    "Background process without a window.": "Hintergrundprozess ohne Fenster.",
    "not running": "läuft nicht",
    "Windows default  (decides itself: {gpu})": "Windows-Standard  (entscheidet selbst: {gpu})",
    # --- overlay: status
    "Preference has no effect – preferred GPU is missing": "Präferenz wirkungslos – bevorzugte GPU fehlt",
    "GPU preference active": "GPU-Präferenz aktiv",
    "Saved – restart {app} to use the new GPU": (
        "Gespeichert – Neustart von {app} nötig, damit die neue GPU genutzt wird"
    ),
    (
        "{app} uses a different GPU despite the preference – the application apparently picks its GPU "
        "itself. Cannot be forced via Windows; only a GPU option inside the application helps."
    ): (
        "{app} nutzt trotz Präferenz eine andere GPU – die Anwendung wählt ihre GPU offenbar selbst. "
        "Über Windows nicht erzwingbar; nur eine GPU-Option in der Anwendung hilft."
    ),
    "Mismatch – restart needed or the application picks its GPU itself": (
        "Abweichung – Neustart nötig oder die Anwendung wählt ihre GPU selbst"
    ),
    "Saved – takes effect after restarting {app}": "Gespeichert – wirksam nach Neustart von {app}",
    "Preference saved – usage currently not measurable": "Präferenz gespeichert – Nutzung derzeit nicht messbar",
    "Reset to Windows default – takes effect after restarting {app}": (
        "Auf Windows-Standard zurückgesetzt – wirksam nach Neustart von {app}"
    ),
    "No own GPU preference": "Keine eigene GPU-Präferenz",
    # --- assignment support
    "No application selected.": "Keine Anwendung ausgewählt.",
    "Game executable not known yet – start the game once to detect it.": (
        "Spiel-EXE noch unbekannt – Spiel einmal starten, dann wird sie erkannt."
    ),
    "Program path not readable (protected process).": "Programmpfad nicht lesbar (geschützter Prozess).",
    "Store apps: please set the GPU under Settings → System → Display → Graphics.": (
        "Store-Apps: GPU bitte unter Einstellungen → System → Anzeige → Grafik festlegen."
    ),
    "Program file no longer exists – only reset is possible.": (
        "Programmdatei existiert nicht mehr – nur Zurücksetzen möglich."
    ),
    "GPU is not present.": "GPU ist nicht vorhanden.",
    "Identical GPUs cannot be told apart by Windows.": "Baugleiche GPUs sind für Windows nicht unterscheidbar.",
    "Takes effect the next time the application starts.": "Wirksam beim nächsten Start der Anwendung.",
    # --- library
    "The path contains the program version and changes with updates.": (
        "Pfad enthält die Programmversion und ändert sich bei Updates."
    ),
    "Starts via {launcher}; the preference applies to {exe}.": "Startet über {launcher}; Präferenz gilt für {exe}.",
    "Game executable detected during the last session.": "Spiel-EXE beim letzten Spielen erkannt.",
    "Game executable estimated (launcher ≠ game process) – confirmed on first play.": (
        "Spiel-EXE geschätzt (Starter ≠ Spielprozess) – wird beim ersten Spielen bestätigt."
    ),
    # --- application list
    "Running": "Laufend",
    "Background (no window)": "Hintergrund (ohne Fenster)",
    "Saved – not running": "Gespeichert – läuft nicht",
    "Installed programs": "Installierte Programme",
    "Installed games": "Installierte Spiele",
    "uses {gpu}": "nutzt {gpu}",
    "no GPU load": "keine GPU-Last",
    "program file missing": "Programmdatei fehlt",
    "executable not known yet": "EXE noch unbekannt",
    "preferred: GPU missing": "bevorzugt: GPU fehlt",
    "preferred {gpu}": "bevorzugt {gpu}",
    # --- overlay window
    "in use": "nutzt",
    "preferred": "bevorzugt",
    "APPLICATIONS": "ANWENDUNGEN",
    "⟳ Rescan": "⟳ Neu einlesen",
    "Rescan installed games and running applications (F5)": (
        "Installierte Spiele und laufende Anwendungen neu einlesen (F5)"
    ),
    "↺  Follow active application": "↺  Aktiver Anwendung folgen",
    "Search …": "Suchen …",
    "⟳ Scanning …": "⟳ Liest ein …",
    "Scanning installed programs and games …": "Installierte Programme und Spiele werden eingelesen …",
    "{apps} programs · {games} games found": "{apps} Programme · {games} Spiele gefunden",
    "☰ Applications": "☰ Anwendungen",
    "Uses": "Nutzt",
    "Preference": "Präferenz",
    "Status": "Status",
    "GRAPHICS CARDS": "GRAFIKKARTEN",
    "GPU FOR THIS APPLICATION": "GPU FÜR DIESE ANWENDUNG",
    "GPU USAGE OF THE APPLICATION": "GPU-NUTZUNG DER ANWENDUNG",
    "Show or hide per-GPU usage (P)": "Nutzung je GPU ein-/ausblenden (P)",
    "Language": "Sprache",
    "Windows language": "Windows-Sprache",
    "The new language is used after the next start.": "Die neue Sprache gilt ab dem nächsten Start.",
    "Apply": "Übernehmen",
    "Choose a GPU (click or ↑/↓) and apply (Enter).": "GPU wählen (Klick oder ↑/↓) und übernehmen (Enter).",
    "📌 Pinned": "📌 Angeheftet",
    "📌 Pin": "📌 Anheften",
    "Pinned · A unpin · L applications · ↑/↓ + Enter choose GPU · Esc closes": (
        "Angeheftet · A lösen · L Anwendungen · ↑/↓ + Enter GPU wählen · Esc schließt"
    ),
    "Esc closes · A pin · L applications · ↑/↓ + Enter GPU · P processes": (
        "Esc schließt · A anheften · L Anwendungen · ↑/↓ + Enter GPU · P Prozesse"
    ),
    # --- tray
    "Open overlay": "Overlay öffnen",
    "Rescan graphics cards and games": "Grafikkarten und Spiele neu einlesen",
    "Start with Windows": "Mit Windows starten",
    "Reset GPU preferences …": "GPU-Präferenzen zurücksetzen …",
    "Open log folder": "Protokollordner öffnen",
    "Quit": "Beenden",
    # --- controller notifications
    "already taken by another application": "bereits von einer anderen Anwendung belegt",
    "error {code}": "Fehler {code}",
    "Hotkey not available": "Tastenkombination nicht verfügbar",
    "{hotkey} is {reason}. Open the overlay via the tray icon.": (
        "{hotkey} ist {reason}. Overlay über das Tray-Symbol öffnen."
    ),
    "Overlay not available in exclusive fullscreen": "Overlay im exklusiven Vollbild nicht verfügbar",
    "{app} is running in exclusive fullscreen.": "{app} läuft im exklusiven Vollbild.",
    "GPU assignment not possible": "GPU-Zuweisung nicht möglich",
    "Saving failed": "Speichern fehlgeschlagen",
    "Nothing to reset": "Nichts zurückzusetzen",
    "SetWhichGPU has not changed any preferences yet.": "SetWhichGPU hat noch keine Präferenzen geändert.",
    "Reset GPU preferences": "GPU-Präferenzen zurücksetzen",
    (
        "Reset all GPU preferences changed by SetWhichGPU ({count} application(s)) "
        "to their original state?\n\nEntries that were changed elsewhere in the meantime stay untouched."
    ): (
        "Alle von SetWhichGPU geänderten GPU-Präferenzen ({count} Anwendung(en)) auf den ursprünglichen "
        "Zustand zurücksetzen?\n\nEinträge, die inzwischen außerhalb geändert wurden, bleiben unverändert."
    ),
    "{n} reset": "{n} zurückgesetzt",
    ", {n} changed elsewhere (left untouched)": ", {n} außerhalb geändert (unverändert gelassen)",
    ", {n} failed": ", {n} fehlgeschlagen",
    "GPU preferences reset": "GPU-Präferenzen zurückgesetzt",
    ". Takes effect after restarting the applications.": ". Wirksam nach Neustart der Anwendungen.",
    "Could not change autostart": "Autostart konnte nicht geändert werden",
    # --- game mode (ADR-0002)
    "🎮 Game mode: disable {gpu} while playing …": "🎮 Spielmodus: {gpu} während des Spielens deaktivieren …",
    "Game mode": "Spielmodus",
    "Game mode active": "Spielmodus aktiv",
    "Game mode ended": "Spielmodus beendet",
    "Game mode failed": "Spielmodus fehlgeschlagen",
    "Game mode not possible": "Spielmodus nicht möglich",
    "Game mode not started": "Spielmodus nicht gestartet",
    "Start game mode?": "Spielmodus starten?",
    "Game mode is already active.": "Der Spielmodus ist bereits aktiv.",
    "The device could not be identified.": "Das Gerät konnte nicht eindeutig erkannt werden.",
    "A monitor is connected to this GPU – it is never disabled.": (
        "An dieser GPU hängt ein Monitor – sie wird nie deaktiviert."
    ),
    "This is the only GPU.": "Das ist die einzige GPU.",
    "The game's executable is unknown.": "Die EXE des Spiels ist unbekannt.",
    "{n} other process(es) are currently computing on this GPU.": (
        "{n} andere(r) Prozess(e) rechnen gerade auf dieser GPU."
    ),
    "{n} other process(es) hold memory on this GPU and may lose it.": (
        "{n} andere(r) Prozess(e) belegen Speicher auf dieser GPU und könnten ihn verlieren."
    ),
    (
        "{app} ignores the Windows GPU preference. Game mode temporarily disables {gpu} so the game "
        "has to use another GPU.\n\n"
        "1. Confirm the Windows administrator prompt.\n"
        "2. Close {app} if it is running – {gpu} is then disabled.\n"
        "3. Start {app} again.\n"
        "4. When you exit the game, {gpu} is enabled again automatically.\n\n"
        "While game mode is active, {gpu} is unavailable for everything else (e.g. CUDA, Blender, "
        "NVIDIA overlay). You can end it at any time from the tray menu."
    ): (
        "{app} ignoriert die GPU-Präferenz von Windows. Der Spielmodus deaktiviert {gpu} vorübergehend, "
        "damit das Spiel eine andere GPU nutzen muss.\n\n"
        "1. Bestätige die Administrator-Abfrage von Windows.\n"
        "2. Beende {app}, falls es läuft – dann wird {gpu} deaktiviert.\n"
        "3. Starte {app} erneut.\n"
        "4. Sobald du das Spiel beendest, wird {gpu} automatisch wieder aktiviert.\n\n"
        "Solange der Spielmodus aktiv ist, steht {gpu} für nichts anderes zur Verfügung (z. B. CUDA, Blender, "
        "NVIDIA-Overlay). Du kannst ihn jederzeit über das Tray-Menü beenden."
    ),
    "The administrator prompt was declined.": "Die Administrator-Abfrage wurde abgelehnt.",
    "Close {app} – then {gpu} will be disabled.": "Beende {app} – danach wird {gpu} deaktiviert.",
    "{gpu} is disabled – start {app} now.": "{gpu} ist deaktiviert – starte jetzt {app}.",
    "{gpu} is enabled again.": "{gpu} ist wieder aktiviert.",
    "{app} was not started in time – {gpu} is enabled again.": (
        "{app} wurde nicht rechtzeitig gestartet – {gpu} ist wieder aktiviert."
    ),
    "End game mode – re-enable {gpu}": "Spielmodus beenden – {gpu} wieder aktivieren",
    "Game mode: waiting for the administrator prompt …": "Spielmodus: warte auf die Administrator-Abfrage …",
    "Game mode: close {app} – then {gpu} will be disabled.": (
        "Spielmodus: Beende {app} – danach wird {gpu} deaktiviert."
    ),
    "Game mode: {gpu} is disabled – start {app} now.": "Spielmodus: {gpu} ist deaktiviert – starte jetzt {app}.",
    "Game mode active: {gpu} is disabled until {app} exits.": (
        "Spielmodus aktiv: {gpu} ist deaktiviert, bis {app} beendet wird."
    ),
    "GPU still disabled": "GPU noch deaktiviert",
    (
        "{gpu} is still disabled from a previous game mode session ({app}). Enable it again now?\n\n"
        "Alternatively: Device Manager → Display adapters → {gpu} → Enable device."
    ): (
        "{gpu} ist von einer früheren Spielmodus-Sitzung ({app}) noch deaktiviert. Jetzt wieder aktivieren?\n\n"
        "Alternativ: Geräte-Manager → Grafikkarten → {gpu} → Gerät aktivieren."
    ),
    "LOADED AI MODELS ({runtime})": "GELADENE KI-MODELLE ({runtime})",
    "{runtime}: loaded models can be shown – tray menu → Show loaded AI models": (
        "{runtime}: geladene Modelle können angezeigt werden – Tray-Menü → Geladene KI-Modelle anzeigen"
    ),
    "Asking the runtime …": "Frage die Laufzeit ab …",
    "The local API requires an API token – not supported.": (
        "Die lokale API verlangt ein API-Token – nicht unterstützt."
    ),
    "{runtime} API not reachable (port {port}) – start the local server in {runtime}.": (
        "{runtime}-API nicht erreichbar (Port {port}) – lokalen Server in {runtime} starten."
    ),
    "{runtime} API not reachable (port {port}).": "{runtime}-API nicht erreichbar (Port {port}).",
    "No model loaded": "Kein Modell geladen",
    "CPU only": "nur CPU",
    "{gpu} % GPU / {cpu} % CPU": "{gpu} % GPU / {cpu} % CPU",
    "Runs on {gpu} (measured)": "Läuft auf {gpu} (gemessen)",
    "Spread over several GPUs (measured): {split}": "Auf mehrere GPUs verteilt (gemessen): {split}",
    "No GPU usage measured right now": "Gerade keine GPU-Nutzung gemessen",
    "Show loaded AI models (Ollama, LM Studio, …)": "Geladene KI-Modelle anzeigen (Ollama, LM Studio, …)",
    "Asks local AI programs on this PC (localhost only) which models are loaded – nothing leaves the PC": (
        "Fragt lokale KI-Programme auf diesem PC (nur localhost), welche Modelle geladen sind – nichts verlässt den PC"
    ),
    "{runtime} is running without its API – start it with {flag} to see the model.": (
        "{runtime} läuft ohne API – mit {flag} starten, um das Modell zu sehen."
    ),
    "{runtime} gave an unexpected answer (port {port}).": "{runtime} hat unerwartet geantwortet (Port {port}).",
    "{gpu} · this app {pct} % load": "{gpu} · diese App {pct} % Last",
    "Total {pct} %": "Gesamt {pct} %",
    "Load of the whole graphics card – all applications together": (
        "Last der ganzen Grafikkarte – alle Anwendungen zusammen"
    ),
    "Last 30 seconds. Card colour: whole graphics card (all apps). White: the selected app.": (
        "Letzte 30 Sekunden. Linie in der Kartenfarbe: ganze Grafikkarte (alle Anwendungen). Weiße "
        "Linie: die gewählte Anwendung."
    ),
    "Share of the selected application in this graphics card's load": (
        "Anteil der gewählten Anwendung an der Last dieser Grafikkarte"
    ),
    "last 30 s": "letzte 30 s",
    "VR game (Meta Horizon Link)": "VR-Spiel (Meta Horizon Link)",
}
