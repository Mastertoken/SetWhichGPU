"""Spanish translations. Keys are the English source strings used with ``tr()``.

``tests/unit/test_i18n.py`` checks completeness and matching placeholders for every catalog.
"""

CATALOG: dict[str, str] = {
    # --- hotkey modifiers
    "Ctrl": "Ctrl",
    "Shift": "Mayús",
    # --- preference kinds
    "Windows default": "Predeterminado de Windows",
    "Power saving": "Ahorro de energía",
    "High performance": "Alto rendimiento",
    "specific GPU": "GPU específica",
    # --- overlay: values
    "{size} reserved · shared memory": "{size} reservados · memoria compartida",
    "shared memory": "memoria compartida",
    "no load": "sin carga",
    "unknown": "desconocido",
    "GPU overview": "Resumen de GPU",
    "No application in the foreground": "Ninguna aplicación en primer plano",
    "No GPU usage detected": "No se detecta uso de GPU",
    "{gpu} · memory in use, currently no load": "{gpu} · memoria en uso, sin carga actualmente",
    "{gpu} · several GPUs, largest memory share": "{gpu} · varias GPU, mayor parte de la memoria",
    "None – Windows decides ({gpu})": "Ninguna – Windows decide ({gpu})",
    "Unknown entry: {raw}": "Entrada desconocida: {raw}",
    "GPU {token} not present – Windows uses its default": ("GPU {token} no presente – Windows usa su predeterminada"),
    "– (not running)": "– (no se está ejecutando)",
    "Not running – the preference applies on next start": (
        "No se está ejecutando – la preferencia se aplica en el próximo inicio"
    ),
    "Not running – no own GPU preference": "No se está ejecutando – sin preferencia de GPU propia",
    "Program file no longer exists (e.g. old version) – the entry can be reset.": (
        "El archivo del programa ya no existe (p. ej. versión antigua) – la entrada se puede restablecer."
    ),
    "Application has exited – values show the last known state.": (
        "La aplicación se ha cerrado – los valores muestran el último estado conocido."
    ),
    "Protected process – path and details not readable.": "Proceso protegido – ruta y detalles no legibles.",
    "Store app detected (resolved via ApplicationFrameHost).": (
        "Aplicación de Store detectada (resuelta mediante ApplicationFrameHost)."
    ),
    "Background process without a window.": "Proceso en segundo plano sin ventana.",
    "not running": "no se está ejecutando",
    "Windows default  (decides itself: {gpu})": "Predeterminado de Windows  (decide por sí mismo: {gpu})",
    # --- overlay: status
    "Preference has no effect – preferred GPU is missing": "La preferencia no tiene efecto – falta la GPU preferida",
    "GPU preference active": "Preferencia de GPU activa",
    "Saved – restart {app} to use the new GPU": "Guardado – reinicia {app} para usar la nueva GPU",
    (
        "{app} uses a different GPU despite the preference – the application apparently picks its GPU "
        "itself. Cannot be forced via Windows; only a GPU option inside the application helps."
    ): (
        "{app} usa otra GPU a pesar de la preferencia – al parecer la aplicación elige la GPU por sí misma. "
        "No se puede forzar desde Windows; solo ayuda una opción de GPU dentro de la aplicación."
    ),
    "Mismatch – restart needed or the application picks its GPU itself": (
        "Discrepancia – hace falta reiniciar o la aplicación elige la GPU por sí misma"
    ),
    "Saved – takes effect after restarting {app}": "Guardado – surte efecto tras reiniciar {app}",
    "Preference saved – usage currently not measurable": "Preferencia guardada – el uso no se puede medir ahora",
    "Reset to Windows default – takes effect after restarting {app}": (
        "Restablecido al predeterminado de Windows – surte efecto tras reiniciar {app}"
    ),
    "No own GPU preference": "Sin preferencia de GPU propia",
    # --- assignment support
    "No application selected.": "No hay ninguna aplicación seleccionada.",
    "Game executable not known yet – start the game once to detect it.": (
        "Ejecutable del juego aún desconocido – inicia el juego una vez para detectarlo."
    ),
    "Program path not readable (protected process).": "Ruta del programa no legible (proceso protegido).",
    "Store apps: please set the GPU under Settings → System → Display → Graphics.": (
        "Aplicaciones de Store: configura la GPU en Configuración → Sistema → Pantalla → Gráficos."
    ),
    "Program file no longer exists – only reset is possible.": (
        "El archivo del programa ya no existe – solo es posible restablecer."
    ),
    "GPU is not present.": "La GPU no está presente.",
    "Identical GPUs cannot be told apart by Windows.": "Windows no puede distinguir GPU idénticas.",
    "Takes effect the next time the application starts.": "Surte efecto la próxima vez que se inicie la aplicación.",
    # --- library
    "The path contains the program version and changes with updates.": (
        "La ruta contiene la versión del programa y cambia con las actualizaciones."
    ),
    "Starts via {launcher}; the preference applies to {exe}.": (
        "Se inicia mediante {launcher}; la preferencia se aplica a {exe}."
    ),
    "Game executable detected during the last session.": "Ejecutable del juego detectado en la última sesión.",
    "Game executable estimated (launcher ≠ game process) – confirmed on first play.": (
        "Ejecutable del juego estimado (lanzador ≠ proceso del juego) – se confirma al jugar por primera vez."
    ),
    # --- application list
    "Running": "En ejecución",
    "Background (no window)": "Segundo plano (sin ventana)",
    "Saved – not running": "Guardado – no se está ejecutando",
    "Installed programs": "Programas instalados",
    "Installed games": "Juegos instalados",
    "uses {gpu}": "usa {gpu}",
    "no GPU load": "sin carga de GPU",
    "program file missing": "falta el archivo del programa",
    "executable not known yet": "ejecutable aún desconocido",
    "preferred: GPU missing": "preferida: falta la GPU",
    "preferred {gpu}": "preferida {gpu}",
    # --- overlay window
    "in use": "en uso",
    "preferred": "preferida",
    "APPLICATIONS": "APLICACIONES",
    "⟳ Rescan": "⟳ Volver a buscar",
    "Rescan installed games and running applications (F5)": (
        "Volver a buscar juegos instalados y aplicaciones en ejecución (F5)"
    ),
    "↺  Follow active application": "↺  Seguir la aplicación activa",
    "Search …": "Buscar …",
    "⟳ Scanning …": "⟳ Buscando …",
    "Scanning installed programs and games …": "Buscando programas y juegos instalados …",
    "{apps} programs · {games} games found": "{apps} programas · {games} juegos encontrados",
    "☰ Applications": "☰ Aplicaciones",
    "Uses": "Usa",
    "Preference": "Preferencia",
    "Status": "Estado",
    "GRAPHICS CARDS": "TARJETAS GRÁFICAS",
    "GPU FOR THIS APPLICATION": "GPU PARA ESTA APLICACIÓN",
    "GPU USAGE OF THE APPLICATION": "USO DE GPU DE LA APLICACIÓN",
    "Show or hide per-GPU usage (P)": "Mostrar u ocultar el uso por GPU (P)",
    "Language": "Idioma",
    "Windows language": "Idioma de Windows",
    "The new language is used after the next start.": "El nuevo idioma se usará a partir del próximo inicio.",
    "Apply": "Aplicar",
    "Choose a GPU (click or ↑/↓) and apply (Enter).": "Elige una GPU (clic o ↑/↓) y aplica (Intro).",
    "📌 Pinned": "📌 Fijado",
    "📌 Pin": "📌 Fijar",
    "Pinned · A unpin · L applications · ↑/↓ + Enter choose GPU · Esc closes": (
        "Fijado · A soltar · L aplicaciones · ↑/↓ + Intro elegir GPU · Esc cierra"
    ),
    "Esc closes · A pin · L applications · ↑/↓ + Enter GPU · P processes": (
        "Esc cierra · A fijar · L aplicaciones · ↑/↓ + Intro GPU · P procesos"
    ),
    # --- tray
    "Open overlay": "Abrir superposición",
    "Rescan graphics cards and games": "Volver a buscar tarjetas gráficas y juegos",
    "Start with Windows": "Iniciar con Windows",
    "Reset GPU preferences …": "Restablecer preferencias de GPU …",
    "Open log folder": "Abrir carpeta de registros",
    "Quit": "Salir",
    # --- controller notifications
    "already taken by another application": "ya está ocupada por otra aplicación",
    "error {code}": "error {code}",
    "Hotkey not available": "Atajo de teclado no disponible",
    "{hotkey} is {reason}. Open the overlay via the tray icon.": (
        "{hotkey}: {reason}. Abre la superposición desde el icono de la bandeja."
    ),
    "Overlay not available in exclusive fullscreen": "Superposición no disponible en pantalla completa exclusiva",
    "{app} is running in exclusive fullscreen.": "{app} se ejecuta en pantalla completa exclusiva.",
    "GPU assignment not possible": "No es posible asignar la GPU",
    "Saving failed": "Error al guardar",
    "Nothing to reset": "Nada que restablecer",
    "SetWhichGPU has not changed any preferences yet.": "SetWhichGPU aún no ha cambiado ninguna preferencia.",
    "Reset GPU preferences": "Restablecer preferencias de GPU",
    (
        "Reset all GPU preferences changed by SetWhichGPU ({count} application(s)) "
        "to their original state?\n\nEntries that were changed elsewhere in the meantime stay untouched."
    ): (
        "¿Restablecer al estado original todas las preferencias de GPU cambiadas por SetWhichGPU "
        "({count} aplicación(es))?\n\nLas entradas que se hayan cambiado por otro medio entretanto no se tocan."
    ),
    "{n} reset": "{n} restablecidas",
    ", {n} changed elsewhere (left untouched)": ", {n} cambiadas por otro medio (sin tocar)",
    ", {n} failed": ", {n} con error",
    "GPU preferences reset": "Preferencias de GPU restablecidas",
    ". Takes effect after restarting the applications.": ". Surte efecto tras reiniciar las aplicaciones.",
    "Could not change autostart": "No se pudo cambiar el inicio automático",
    # --- game mode (ADR-0002)
    "🎮 Game mode: disable {gpu} while playing …": "🎮 Modo juego: desactivar {gpu} mientras juegas …",
    "Game mode": "Modo juego",
    "Game mode active": "Modo juego activo",
    "Game mode ended": "Modo juego finalizado",
    "Game mode failed": "Error en el modo juego",
    "Game mode not possible": "Modo juego no disponible",
    "Game mode not started": "Modo juego no iniciado",
    "Start game mode?": "¿Iniciar el modo juego?",
    "Game mode is already active.": "El modo juego ya está activo.",
    "The device could not be identified.": "No se pudo identificar el dispositivo.",
    "A monitor is connected to this GPU – it is never disabled.": (
        "Hay un monitor conectado a esta GPU – nunca se desactiva."
    ),
    "This is the only GPU.": "Esta es la única GPU.",
    "The game's executable is unknown.": "El ejecutable del juego es desconocido.",
    "{n} other process(es) are currently computing on this GPU.": (
        "{n} proceso(s) más están calculando en esta GPU ahora mismo."
    ),
    "{n} other process(es) hold memory on this GPU and may lose it.": (
        "{n} proceso(s) más ocupan memoria en esta GPU y podrían perderla."
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
        "{app} ignora la preferencia de GPU de Windows. El modo juego desactiva {gpu} temporalmente "
        "para que el juego tenga que usar otra GPU.\n\n"
        "1. Confirma la solicitud de administrador de Windows.\n"
        "2. Cierra {app} si se está ejecutando – entonces se desactiva {gpu}.\n"
        "3. Vuelve a iniciar {app}.\n"
        "4. Al salir del juego, {gpu} se vuelve a activar automáticamente.\n\n"
        "Mientras el modo juego está activo, {gpu} no está disponible para nada más (p. ej. CUDA, Blender, "
        "superposición de NVIDIA). Puedes finalizarlo en cualquier momento desde el menú de la bandeja."
    ),
    "The administrator prompt was declined.": "Se rechazó la solicitud de administrador.",
    "Close {app} – then {gpu} will be disabled.": "Cierra {app} – después se desactivará {gpu}.",
    "{gpu} is disabled – start {app} now.": "{gpu} está desactivada – inicia {app} ahora.",
    "{gpu} is enabled again.": "{gpu} vuelve a estar activada.",
    "{app} was not started in time – {gpu} is enabled again.": (
        "{app} no se inició a tiempo – {gpu} vuelve a estar activada."
    ),
    "End game mode – re-enable {gpu}": "Finalizar modo juego – reactivar {gpu}",
    "Game mode: waiting for the administrator prompt …": "Modo juego: esperando la solicitud de administrador …",
    "Game mode: close {app} – then {gpu} will be disabled.": (
        "Modo juego: cierra {app} – después se desactivará {gpu}."
    ),
    "Game mode: {gpu} is disabled – start {app} now.": "Modo juego: {gpu} está desactivada – inicia {app} ahora.",
    "Game mode active: {gpu} is disabled until {app} exits.": (
        "Modo juego activo: {gpu} está desactivada hasta que se cierre {app}."
    ),
    "GPU still disabled": "GPU aún desactivada",
    (
        "{gpu} is still disabled from a previous game mode session ({app}). Enable it again now?\n\n"
        "Alternatively: Device Manager → Display adapters → {gpu} → Enable device."
    ): (
        "{gpu} sigue desactivada por una sesión anterior del modo juego ({app}). ¿Activarla ahora?\n\n"
        "Alternativa: Administrador de dispositivos → Adaptadores de pantalla → {gpu} → Habilitar dispositivo."
    ),
    "LOADED AI MODELS ({runtime})": "MODELOS DE IA CARGADOS ({runtime})",
    "{runtime}: loaded models can be shown – tray menu → Show loaded AI models": (
        "{runtime}: se pueden mostrar los modelos cargados – menú de la bandeja → Mostrar modelos de IA cargados"
    ),
    "Asking the runtime …": "Consultando el entorno …",
    "The local API requires an API token – not supported.": "La API local requiere un token – no compatible.",
    "{runtime} API not reachable (port {port}) – start the local server in {runtime}.": (
        "API de {runtime} no disponible (puerto {port}) – inicia el servidor local en {runtime}."
    ),
    "{runtime} API not reachable (port {port}).": "API de {runtime} no disponible (puerto {port}).",
    "No model loaded": "Ningún modelo cargado",
    "CPU only": "solo CPU",
    "{gpu} % GPU / {cpu} % CPU": "{gpu} % GPU / {cpu} % CPU",
    "Runs on {gpu} (measured)": "Se ejecuta en {gpu} (medido)",
    "Spread over several GPUs (measured): {split}": "Repartido en varias GPU (medido): {split}",
    "No GPU usage measured right now": "Ahora mismo no se mide uso de GPU",
    "Show loaded AI models (Ollama, LM Studio, …)": "Mostrar modelos de IA cargados (Ollama, LM Studio, …)",
    "Asks local AI programs on this PC (localhost only) which models are loaded – nothing leaves the PC": (
        "Pregunta a los programas de IA locales de este PC (solo localhost) qué modelos están "
        "cargados – nada sale del PC"
    ),
    "{runtime} is running without its API – start it with {flag} to see the model.": (
        "{runtime} se ejecuta sin API – inícialo con {flag} para ver el modelo."
    ),
    "{runtime} gave an unexpected answer (port {port}).": "{runtime} dio una respuesta inesperada (puerto {port}).",
    "{gpu} · this app {pct} % load": "{gpu} · esta app {pct} % de carga",
    "Total {pct} %": "Total {pct} %",
    "Load of the whole graphics card – all applications together": (
        "Carga de toda la tarjeta gráfica – todas las aplicaciones juntas"
    ),
    "Last 30 seconds. Card colour: whole graphics card (all apps). White: the selected app.": (
        "Últimos 30 segundos. Línea del color de la tarjeta: toda la tarjeta gráfica (todas las "
        "aplicaciones). Línea blanca: la aplicación seleccionada."
    ),
    "Share of the selected application in this graphics card's load": (
        "Parte de la aplicación seleccionada en la carga de esta tarjeta gráfica"
    ),
    "last 30 s": "últimos 30 s",
    "VR game (Meta Horizon Link)": "Juego de RV (Meta Horizon Link)",
    "Added by you": "Añadidos por ti",
    "＋ Add program …": "＋ Añadir programa …",
    "Add a program that is not listed – choose its .exe file": (
        "Añadir un programa que no aparece – elige su archivo .exe"
    ),
    "Remove from list": "Quitar de la lista",
    "Add program": "Añadir programa",
    "Programs (*.exe)": "Programas (*.exe)",
    "Program not added": "Programa no añadido",
    "Please choose an existing program file (.exe).": "Elige un archivo de programa (.exe) existente.",
}
