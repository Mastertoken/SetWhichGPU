"""Minimal message catalog: English source strings, translations per language (pure).

Usage::

    from gpucc.i18n import tr
    tr("Restart {app} to use the new GPU", app=name)

The language defaults to the Windows UI language (``GPUCC_LANG`` overrides, e.g. ``en``/``de``).
Missing translations fall back to English; ``{placeholders}`` must exist in every translation.
"""

from __future__ import annotations

import os

from gpucc.i18n.de import CATALOG as _DE
from gpucc.i18n.es import CATALOG as _ES
from gpucc.i18n.fr import CATALOG as _FR

SUPPORTED = ("en", "de", "es", "fr")
CATALOGS: dict[str, dict[str, str]] = {"de": _DE, "es": _ES, "fr": _FR}
# Windows primary language ids (LANGID & 0x3FF) → catalog
_PRIMARY_LANGUAGE = {0x07: "de", 0x0A: "es", 0x0C: "fr"}
_COMMA_DECIMAL = frozenset({"de", "es", "fr"})
_language = "en"


def system_language(ui_lang_id: int | None) -> str:
    """Language for a Windows UI LANGID (supported ones, else 'en'); GPUCC_LANG overrides."""
    override = os.environ.get("GPUCC_LANG", "").lower()
    if override in SUPPORTED:
        return override
    if ui_lang_id is None:
        return "en"
    return _PRIMARY_LANGUAGE.get(ui_lang_id & 0x3FF, "en")


SYSTEM = "system"


def resolve_language(setting: str | None, ui_lang_id: int | None) -> str:
    """Effective language: GPUCC_LANG, else the user's choice ('en'/'de'), else the Windows UI language."""
    override = os.environ.get("GPUCC_LANG", "").lower()
    if override in SUPPORTED:
        return override
    if setting in SUPPORTED:
        return setting
    return system_language(ui_lang_id)


def set_language(lang: str) -> None:
    global _language  # noqa: PLW0603 – process-wide UI setting
    _language = lang if lang in SUPPORTED else "en"


def language() -> str:
    return _language


def tr(msgid: str, **kwargs: object) -> str:
    text = CATALOGS.get(_language, {}).get(msgid, msgid)
    return text.format(**kwargs) if kwargs else text


def decimal_separator() -> str:
    return "," if _language in _COMMA_DECIMAL else "."
