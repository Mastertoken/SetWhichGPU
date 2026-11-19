"""Clean text that comes from other programs (local AI APIs, launcher files) before it is displayed.

Removes control characters, invisible formatting characters (e.g. U+202E right-to-left override, which
can disguise a name), unassigned/private/surrogate code points and line/paragraph separators, collapses
whitespace and caps the length. The overlay additionally shows such text as plain text only.
"""

from __future__ import annotations

import unicodedata

_HIDDEN = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def clean_text(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    text = "".join(" " if unicodedata.category(ch) in _HIDDEN else ch for ch in value[: limit * 4])
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
