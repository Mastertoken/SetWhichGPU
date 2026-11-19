"""French translations. Keys are the English source strings used with ``tr()``.

``tests/unit/test_i18n.py`` checks completeness and matching placeholders for every catalog.
"""

CATALOG: dict[str, str] = {
    # --- hotkey modifiers
    "Ctrl": "Ctrl",
    "Shift": "Maj",
    # --- preference kinds
    "Windows default": "Valeur par défaut de Windows",
    "Power saving": "Économie d'énergie",
    "High performance": "Hautes performances",
    "specific GPU": "GPU spécifique",
    # --- overlay: values
    "{size} reserved · shared memory": "{size} réservés · mémoire partagée",
    "shared memory": "mémoire partagée",
    "no load": "aucune charge",
    "unknown": "inconnu",
    "GPU overview": "Vue d'ensemble des GPU",
    "No application in the foreground": "Aucune application au premier plan",
    "No GPU usage detected": "Aucune utilisation du GPU détectée",
    "{gpu} · memory in use, currently no load": "{gpu} · mémoire utilisée, aucune charge actuellement",
    "{gpu} · several GPUs, largest memory share": "{gpu} · plusieurs GPU, plus grande part de mémoire",
    "None – Windows decides ({gpu})": "Aucune – Windows décide ({gpu})",
    "Unknown entry: {raw}": "Entrée inconnue : {raw}",
    "GPU {token} not present – Windows uses its default": ("GPU {token} absent – Windows utilise sa valeur par défaut"),
    "– (not running)": "– (non lancé)",
    "Not running – the preference applies on next start": (
        "Non lancé – la préférence s'applique au prochain démarrage"
    ),
    "Not running – no own GPU preference": "Non lancé – aucune préférence GPU propre",
    "Program file no longer exists (e.g. old version) – the entry can be reset.": (
        "Le fichier du programme n'existe plus (p. ex. ancienne version) – l'entrée peut être réinitialisée."
    ),
    "Application has exited – values show the last known state.": (
        "L'application a été fermée – les valeurs indiquent le dernier état connu."
    ),
    "Protected process – path and details not readable.": "Processus protégé – chemin et détails illisibles.",
    "Store app detected (resolved via ApplicationFrameHost).": (
        "Application du Store détectée (résolue via ApplicationFrameHost)."
    ),
    "Background process without a window.": "Processus en arrière-plan sans fenêtre.",
    "not running": "non lancé",
    "Windows default  (decides itself: {gpu})": "Valeur par défaut de Windows  (décide lui-même : {gpu})",
    # --- overlay: status
    "Preference has no effect – preferred GPU is missing": "Préférence sans effet – le GPU préféré est absent",
    "GPU preference active": "Préférence GPU active",
    "Saved – restart {app} to use the new GPU": "Enregistré – redémarrez {app} pour utiliser le nouveau GPU",
    (
        "{app} uses a different GPU despite the preference – the application apparently picks its GPU "
        "itself. Cannot be forced via Windows; only a GPU option inside the application helps."
    ): (
        "{app} utilise un autre GPU malgré la préférence – l'application choisit apparemment son GPU "
        "elle-même. Impossible à forcer via Windows ; seule une option GPU dans l'application peut aider."
    ),
    "Mismatch – restart needed or the application picks its GPU itself": (
        "Écart – redémarrage nécessaire ou l'application choisit son GPU elle-même"
    ),
    "Saved – takes effect after restarting {app}": "Enregistré – effectif après le redémarrage de {app}",
    "Preference saved – usage currently not measurable": (
        "Préférence enregistrée – utilisation non mesurable pour le moment"
    ),
    "Reset to Windows default – takes effect after restarting {app}": (
        "Réinitialisé à la valeur par défaut de Windows – effectif après le redémarrage de {app}"
    ),
    "No own GPU preference": "Aucune préférence GPU propre",
    # --- assignment support
    "No application selected.": "Aucune application sélectionnée.",
    "Game executable not known yet – start the game once to detect it.": (
        "Exécutable du jeu encore inconnu – lancez le jeu une fois pour le détecter."
    ),
    "Program path not readable (protected process).": "Chemin du programme illisible (processus protégé).",
    "Store apps: please set the GPU under Settings → System → Display → Graphics.": (
        "Applications du Store : définissez le GPU dans Paramètres → Système → Écran → Graphiques."
    ),
    "Program file no longer exists – only reset is possible.": (
        "Le fichier du programme n'existe plus – seule la réinitialisation est possible."
    ),
    "GPU is not present.": "Le GPU est absent.",
    "Identical GPUs cannot be told apart by Windows.": "Windows ne peut pas distinguer des GPU identiques.",
    "Takes effect the next time the application starts.": "Effectif au prochain démarrage de l'application.",
    # --- library
    "The path contains the program version and changes with updates.": (
        "Le chemin contient la version du programme et change avec les mises à jour."
    ),
    "Starts via {launcher}; the preference applies to {exe}.": (
        "Démarre via {launcher} ; la préférence s'applique à {exe}."
    ),
    "Game executable detected during the last session.": "Exécutable du jeu détecté lors de la dernière session.",
    "Game executable estimated (launcher ≠ game process) – confirmed on first play.": (
        "Exécutable du jeu estimé (lanceur ≠ processus du jeu) – confirmé lors de la première partie."
    ),
    # --- application list
    "Running": "En cours d'exécution",
    "Background (no window)": "Arrière-plan (sans fenêtre)",
    "Saved – not running": "Enregistré – non lancé",
    "Installed programs": "Programmes installés",
    "Installed games": "Jeux installés",
    "uses {gpu}": "utilise {gpu}",
    "no GPU load": "aucune charge GPU",
    "program file missing": "fichier du programme manquant",
    "executable not known yet": "exécutable encore inconnu",
    "preferred: GPU missing": "préféré : GPU absent",
    "preferred {gpu}": "préféré {gpu}",
    # --- overlay window
    "in use": "utilisé",
    "preferred": "préféré",
    "APPLICATIONS": "APPLICATIONS",
    "⟳ Rescan": "⟳ Actualiser",
    "Rescan installed games and running applications (F5)": (
        "Actualiser les jeux installés et les applications en cours (F5)"
    ),
    "↺  Follow active application": "↺  Suivre l'application active",
    "Search …": "Rechercher …",
    "⟳ Scanning …": "⟳ Analyse …",
    "Scanning installed programs and games …": "Analyse des programmes et jeux installés …",
    "{apps} programs · {games} games found": "{apps} programmes · {games} jeux trouvés",
    "☰ Applications": "☰ Applications",
    "Uses": "Utilise",
    "Preference": "Préférence",
    "Status": "État",
    "GRAPHICS CARDS": "CARTES GRAPHIQUES",
    "GPU FOR THIS APPLICATION": "GPU POUR CETTE APPLICATION",
    "GPU USAGE OF THE APPLICATION": "UTILISATION GPU DE L'APPLICATION",
    "Show or hide per-GPU usage (P)": "Afficher ou masquer l'utilisation par GPU (P)",
    "Language": "Langue",
    "Windows language": "Langue de Windows",
    "The new language is used after the next start.": "La nouvelle langue sera utilisée au prochain démarrage.",
    "Apply": "Appliquer",
    "Choose a GPU (click or ↑/↓) and apply (Enter).": "Choisissez un GPU (clic ou ↑/↓) et appliquez (Entrée).",
    "📌 Pinned": "📌 Épinglé",
    "📌 Pin": "📌 Épingler",
    "Pinned · A unpin · L applications · ↑/↓ + Enter choose GPU · Esc closes": (
        "Épinglé · A détacher · L applications · ↑/↓ + Entrée choisir le GPU · Échap ferme"
    ),
    "Esc closes · A pin · L applications · ↑/↓ + Enter GPU · P processes": (
        "Échap ferme · A épingler · L applications · ↑/↓ + Entrée GPU · P processus"
    ),
    # --- tray
    "Open overlay": "Ouvrir la superposition",
    "Rescan graphics cards and games": "Actualiser les cartes graphiques et les jeux",
    "Start with Windows": "Lancer avec Windows",
    "Reset GPU preferences …": "Réinitialiser les préférences GPU …",
    "Open log folder": "Ouvrir le dossier des journaux",
    "Quit": "Quitter",
    # --- controller notifications
    "already taken by another application": "déjà utilisé par une autre application",
    "error {code}": "erreur {code}",
    "Hotkey not available": "Raccourci clavier indisponible",
    "{hotkey} is {reason}. Open the overlay via the tray icon.": (
        "{hotkey} : {reason}. Ouvrez la superposition via l'icône de la zone de notification."
    ),
    "Overlay not available in exclusive fullscreen": "Superposition indisponible en plein écran exclusif",
    "{app} is running in exclusive fullscreen.": "{app} est en plein écran exclusif.",
    "GPU assignment not possible": "Attribution du GPU impossible",
    "Saving failed": "Échec de l'enregistrement",
    "Nothing to reset": "Rien à réinitialiser",
    "SetWhichGPU has not changed any preferences yet.": "SetWhichGPU n'a encore modifié aucune préférence.",
    "Reset GPU preferences": "Réinitialiser les préférences GPU",
    (
        "Reset all GPU preferences changed by SetWhichGPU ({count} application(s)) "
        "to their original state?\n\nEntries that were changed elsewhere in the meantime stay untouched."
    ): (
        "Rétablir l'état d'origine de toutes les préférences GPU modifiées par SetWhichGPU "
        "({count} application(s)) ?\n\nLes entrées modifiées ailleurs entre-temps restent inchangées."
    ),
    "{n} reset": "{n} réinitialisée(s)",
    ", {n} changed elsewhere (left untouched)": ", {n} modifiée(s) ailleurs (inchangée(s))",
    ", {n} failed": ", {n} en échec",
    "GPU preferences reset": "Préférences GPU réinitialisées",
    ". Takes effect after restarting the applications.": ". Effectif après le redémarrage des applications.",
    "Could not change autostart": "Impossible de modifier le démarrage automatique",
    # --- game mode (ADR-0002)
    "🎮 Game mode: disable {gpu} while playing …": "🎮 Mode jeu : désactiver {gpu} pendant la partie …",
    "Game mode": "Mode jeu",
    "Game mode active": "Mode jeu actif",
    "Game mode ended": "Mode jeu terminé",
    "Game mode failed": "Échec du mode jeu",
    "Game mode not possible": "Mode jeu impossible",
    "Game mode not started": "Mode jeu non démarré",
    "Start game mode?": "Démarrer le mode jeu ?",
    "Game mode is already active.": "Le mode jeu est déjà actif.",
    "The device could not be identified.": "Le périphérique n'a pas pu être identifié.",
    "A monitor is connected to this GPU – it is never disabled.": (
        "Un écran est branché sur ce GPU – il n'est jamais désactivé."
    ),
    "This is the only GPU.": "C'est le seul GPU.",
    "The game's executable is unknown.": "L'exécutable du jeu est inconnu.",
    "{n} other process(es) are currently computing on this GPU.": (
        "{n} autre(s) processus calcule(nt) actuellement sur ce GPU."
    ),
    "{n} other process(es) hold memory on this GPU and may lose it.": (
        "{n} autre(s) processus occupe(nt) de la mémoire sur ce GPU et pourrai(en)t la perdre."
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
        "{app} ignore la préférence GPU de Windows. Le mode jeu désactive temporairement {gpu} afin que "
        "le jeu doive utiliser un autre GPU.\n\n"
        "1. Confirmez la demande d'administrateur de Windows.\n"
        "2. Fermez {app} s'il est lancé – {gpu} est alors désactivé.\n"
        "3. Relancez {app}.\n"
        "4. Quand vous quittez le jeu, {gpu} est automatiquement réactivé.\n\n"
        "Tant que le mode jeu est actif, {gpu} n'est disponible pour rien d'autre (p. ex. CUDA, Blender, "
        "superposition NVIDIA). Vous pouvez y mettre fin à tout moment depuis le menu de la zone de notification."
    ),
    "The administrator prompt was declined.": "La demande d'administrateur a été refusée.",
    "Close {app} – then {gpu} will be disabled.": "Fermez {app} – {gpu} sera ensuite désactivé.",
    "{gpu} is disabled – start {app} now.": "{gpu} est désactivé – lancez {app} maintenant.",
    "{gpu} is enabled again.": "{gpu} est de nouveau activé.",
    "{app} was not started in time – {gpu} is enabled again.": (
        "{app} n'a pas été lancé à temps – {gpu} est de nouveau activé."
    ),
    "End game mode – re-enable {gpu}": "Terminer le mode jeu – réactiver {gpu}",
    "Game mode: waiting for the administrator prompt …": "Mode jeu : en attente de la demande d'administrateur …",
    "Game mode: close {app} – then {gpu} will be disabled.": "Mode jeu : fermez {app} – {gpu} sera ensuite désactivé.",
    "Game mode: {gpu} is disabled – start {app} now.": "Mode jeu : {gpu} est désactivé – lancez {app} maintenant.",
    "Game mode active: {gpu} is disabled until {app} exits.": (
        "Mode jeu actif : {gpu} est désactivé jusqu'à la fermeture de {app}."
    ),
    "GPU still disabled": "GPU toujours désactivé",
    (
        "{gpu} is still disabled from a previous game mode session ({app}). Enable it again now?\n\n"
        "Alternatively: Device Manager → Display adapters → {gpu} → Enable device."
    ): (
        "{gpu} est encore désactivé suite à une session de mode jeu précédente ({app}). Le réactiver maintenant ?\n\n"
        "Sinon : Gestionnaire de périphériques → Cartes graphiques → {gpu} → Activer le périphérique."
    ),
    "LOADED AI MODELS ({runtime})": "MODÈLES D'IA CHARGÉS ({runtime})",
    "{runtime}: loaded models can be shown – tray menu → Show loaded AI models": (
        "{runtime} : les modèles chargés peuvent être affichés – menu de la zone de notification → Afficher "
        "les modèles d'IA chargés"
    ),
    "Asking the runtime …": "Interrogation de l'environnement …",
    "The local API requires an API token – not supported.": "L'API locale exige un jeton – non pris en charge.",
    "{runtime} API not reachable (port {port}) – start the local server in {runtime}.": (
        "API de {runtime} injoignable (port {port}) – démarrez le serveur local dans {runtime}."
    ),
    "{runtime} API not reachable (port {port}).": "API de {runtime} injoignable (port {port}).",
    "No model loaded": "Aucun modèle chargé",
    "CPU only": "CPU uniquement",
    "{gpu} % GPU / {cpu} % CPU": "{gpu} % GPU / {cpu} % CPU",
    "Runs on {gpu} (measured)": "Tourne sur {gpu} (mesuré)",
    "Spread over several GPUs (measured): {split}": "Réparti sur plusieurs GPU (mesuré) : {split}",
    "No GPU usage measured right now": "Aucune utilisation GPU mesurée pour le moment",
    "Show loaded AI models (Ollama, LM Studio, …)": "Afficher les modèles d'IA chargés (Ollama, LM Studio, …)",
    "Asks local AI programs on this PC (localhost only) which models are loaded – nothing leaves the PC": (
        "Demande aux programmes d'IA locaux de ce PC (localhost uniquement) quels modèles sont "
        "chargés – rien ne quitte le PC"
    ),
    "{runtime} is running without its API – start it with {flag} to see the model.": (
        "{runtime} tourne sans API – lancez-le avec {flag} pour voir le modèle."
    ),
    "{runtime} gave an unexpected answer (port {port}).": "{runtime} a donné une réponse inattendue (port {port}).",
    "{gpu} · this app {pct} % load": "{gpu} · cette app {pct} % de charge",
    "Total {pct} %": "Total {pct} %",
    "Load of the whole graphics card – all applications together": (
        "Charge de toute la carte graphique – toutes les applications ensemble"
    ),
    "Last 30 seconds. Card colour: whole graphics card (all apps). White: the selected app.": (
        "30 dernières secondes. Ligne de la couleur de la carte : toute la carte graphique (toutes les "
        "applications). Ligne blanche : l'application sélectionnée."
    ),
    "Share of the selected application in this graphics card's load": (
        "Part de l'application sélectionnée dans la charge de cette carte graphique"
    ),
    "last 30 s": "30 dernières s",
    "VR game (Meta Horizon Link)": "Jeu VR (Meta Horizon Link)",
    "Added by you": "Ajoutés par vous",
    "+ Add program …": "+ Ajouter un programme …",
    "Add a program that is not listed – choose its .exe file": (
        "Ajouter un programme absent de la liste – choisissez son fichier .exe"
    ),
    "Remove from list": "Retirer de la liste",
    "Add program": "Ajouter un programme",
    "Programs (*.exe)": "Programmes (*.exe)",
    "Program not added": "Programme non ajouté",
    "Please choose an existing program file (.exe).": "Choisissez un fichier programme (.exe) existant.",
    "Loading applications and games …": "Chargement des applications et des jeux …",
}
