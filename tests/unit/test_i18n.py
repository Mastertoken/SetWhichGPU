"""Catalog completeness: every tr("…") literal in src has an entry in every catalog with matching placeholders."""

import ast
import string
from pathlib import Path

import pytest

from gpucc.i18n import CATALOGS, SUPPORTED, decimal_separator, set_language, tr

SRC = Path(__file__).resolve().parents[2] / "src" / "gpucc"


def source_msgids() -> set[str]:
    ids: set[str] = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                ids.add(node.args[0].value)
    return ids


def fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_language_has_a_catalog():
    assert set(CATALOGS) == set(SUPPORTED) - {"en"}


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_every_source_string_is_translated(lang):
    missing = sorted(source_msgids() - set(CATALOGS[lang]))
    assert not missing, f"missing {lang} translations: {missing}"


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_no_stale_catalog_entries(lang):
    hotkey_display = {"Ctrl", "Shift"}  # passed to tr() via a variable in core/hotkey.py
    stale = sorted(set(CATALOGS[lang]) - source_msgids() - hotkey_display)
    assert not stale, f"unused {lang} catalog entries: {stale}"


@pytest.mark.parametrize(
    ("lang", "msgid", "text"),
    [(lang, k, v) for lang, cat in sorted(CATALOGS.items()) for k, v in sorted(cat.items())],
)
def test_placeholders_match(lang, msgid, text):
    assert fields(msgid) == fields(text), lang


@pytest.mark.parametrize("lang", sorted(CATALOGS))
def test_tray_language_names_and_hotkey_round_trip(lang):
    from gpucc.core.hotkey import parse_hotkey

    set_language(lang)
    hk = parse_hotkey("Ctrl+Shift+F9")
    assert parse_hotkey(str(hk)) == hk  # the localized display can be parsed back
    set_language("de")


def test_system_language(monkeypatch):
    from gpucc.i18n import system_language

    monkeypatch.delenv("GPUCC_LANG", raising=False)
    assert system_language(0x0407) == "de"  # de-DE
    assert system_language(0x0C07) == "de"  # de-AT
    assert system_language(0x0409) == "en"  # en-US
    assert system_language(0x040C) == "fr"  # fr-FR
    assert system_language(0x0C0C) == "fr"  # fr-CA
    assert system_language(0x0C0A) == "es"  # es-ES
    assert system_language(0x080A) == "es"  # es-MX
    assert system_language(0x0410) == "en"  # it-IT → fallback
    assert system_language(None) == "en"
    monkeypatch.setenv("GPUCC_LANG", "en")
    assert system_language(0x0407) == "en"


def test_saved_language_choice(monkeypatch):
    from gpucc.i18n import resolve_language

    monkeypatch.delenv("GPUCC_LANG", raising=False)
    assert resolve_language("en", 0x0407) == "en"  # user picked English on a German Windows
    assert resolve_language("de", 0x0409) == "de"
    assert resolve_language("system", 0x0407) == "de"
    assert resolve_language(None, 0x0409) == "en"
    monkeypatch.setenv("GPUCC_LANG", "de")
    assert resolve_language("en", 0x0409) == "de"  # explicit override wins


def test_tray_language_menu(qtbot):
    from gpucc.ui.tray import TrayService

    tray = TrayService("Strg+Alt+G", language="en")
    chosen: list[str] = []
    tray.language_chosen.connect(chosen.append)
    assert tray._language_actions["en"].isChecked()
    tray._language_actions["de"].trigger()
    assert chosen == ["de"] and tray._language_actions["de"].isChecked()
    tray.set_language_checked("system")
    assert tray._language_actions["system"].isChecked() and not tray._language_actions["de"].isChecked()
    assert set(tray._language_actions) == {"system", *SUPPORTED}


def test_language_switch():
    from gpucc.core.hotkey import parse_hotkey
    from gpucc.ui.overlay.viewmodel import de

    set_language("en")
    assert tr("GPU preference active") == "GPU preference active"
    assert str(parse_hotkey("Strg+Alt+G")) == "Ctrl+Alt+G"
    assert decimal_separator() == "." and de(9.84) == "9.8"
    set_language("de")
    assert tr("GPU preference active") == "GPU-Präferenz aktiv"
    assert str(parse_hotkey("Ctrl+Alt+G")) == "Strg+Alt+G"
    assert de(9.84) == "9,8"
    set_language("fr")
    assert tr("Apply") == "Appliquer" and de(9.84) == "9,8"
    set_language("es")
    assert tr("Apply") == "Aplicar"
    set_language("it")  # unsupported → English
    assert tr("Apply") == "Apply"
