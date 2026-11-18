import pytest

from gpucc.core.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, Hotkey, parse_hotkey


@pytest.mark.parametrize("text", ["Strg+Alt+G", "ctrl+alt+g", " Ctrl + Alt + G "])
def test_default_variants(text):
    assert parse_hotkey(text) == Hotkey(MOD_CONTROL | MOD_ALT, ord("G"))


def test_function_key_and_format():
    hk = parse_hotkey("Umschalt+Strg+F9")
    assert hk == Hotkey(MOD_CONTROL | MOD_SHIFT, 0x78)
    assert str(hk) == "Strg+Umschalt+F9"
    assert str(parse_hotkey("Ctrl+Alt+G")) == "Strg+Alt+G"


@pytest.mark.parametrize("bad", ["G", "Strg+", "Hyper+G", "Strg+Ä", "Strg+Alt+Enter"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)
