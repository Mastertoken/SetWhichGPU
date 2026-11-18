"""Hotkey parsing/formatting (pure). Modifier values match Win32 ``RegisterHotKey``."""

from __future__ import annotations

from dataclasses import dataclass

from gpucc.i18n import tr

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {
    "ctrl": MOD_CONTROL,
    "strg": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "umschalt": MOD_SHIFT,
    "mayús": MOD_SHIFT,
    "mayus": MOD_SHIFT,
    "maj": MOD_SHIFT,
    "win": MOD_WIN,
}
_NAMED_KEYS = {
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    "space": 0x20,
    "leertaste": 0x20,
    "pause": 0x13,
    "home": 0x24,
    "pos1": 0x24,
    "end": 0x23,
    "ende": 0x23,
    "insert": 0x2D,
    "einfg": 0x2D,
}
_DISPLAY_MODS = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))

DEFAULT_HOTKEY = "Ctrl+Alt+G"


@dataclass(frozen=True, slots=True)
class Hotkey:
    modifiers: int
    vk: int

    def __str__(self) -> str:
        """Localized display ('Strg+Alt+G' in German, 'Ctrl+Alt+G' in English)."""
        parts = [tr(name) for flag, name in _DISPLAY_MODS if self.modifiers & flag]
        key = next((k.upper() for k, v in _NAMED_KEYS.items() if v == self.vk and k[0] == "f"), None)
        parts.append(key or chr(self.vk))
        return "+".join(parts)


def parse_hotkey(text: str) -> Hotkey:
    """Parse ``"Strg+Alt+G"`` / ``"Ctrl+Alt+F9"``. Requires at least one modifier."""
    tokens = [t.strip().lower() for t in text.split("+") if t.strip()]
    if len(tokens) < 2:
        raise ValueError(f"hotkey needs at least one modifier: {text!r}")
    mods = 0
    for t in tokens[:-1]:
        if t not in _MODS:
            raise ValueError(f"unknown modifier {t!r} in {text!r}")
        mods |= _MODS[t]
    key = tokens[-1]
    if key in _NAMED_KEYS:
        vk = _NAMED_KEYS[key]
    elif len(key) == 1 and (key.isascii() and key.isalnum()):
        vk = ord(key.upper())
    else:
        raise ValueError(f"unsupported key {key!r} in {text!r}")
    return Hotkey(mods, vk)
