"""Product name and legacy identifiers (for migrating data of the former 'GPU Control Center')."""

APP_NAME = "SetWhichGPU"
TAGLINE = "See and set which GPU every Windows app uses"

LEGACY_DATA_DIR = "GpuControlCenter"
LEGACY_AUTOSTART_NAME = "GPU Control Center"

# App-wide identifiers that the entry point needs before Qt is loaded.
LANGUAGE_SETTING = "language"
LOCALAI_SETTING = "localai"  # unset/"1" = ask local AI runtimes on localhost for loaded models (ADR-0003)
RESTART_FLAG = "--restart"
