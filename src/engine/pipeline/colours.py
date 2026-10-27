"""Colour words sellers say (Hindi in Roman and Devanagari script, and English).

Used to link a spoken price to the item it describes ("agla hara wala" = the next green one)
when timing alone is ambiguous.
"""

from __future__ import annotations

import re

from engine.prices.numbers import normalise_devanagari

_COLOURS: dict[str, tuple[str, ...]] = {
    "blue": ("blue", "neela", "neeli", "neele", "nila", "nili", "नीला", "नीली", "नीले", "navy"),
    "sky": ("sky", "aasmani", "asmani", "आसमानी", "light blue"),
    "red": ("red", "laal", "lal", "लाल"),
    "green": ("green", "hara", "hari", "hare", "हरा", "हरी", "हरे"),
    "yellow": ("yellow", "peela", "peeli", "peele", "pila", "pili", "पीला", "पीली", "पीले"),
    "pink": ("pink", "gulabi", "गुलाबी", "rani"),
    "black": ("black", "kaala", "kala", "kaali", "kali", "kaale", "काला", "काली", "काले"),
    "white": ("white", "safed", "safaid", "सफेद", "सफ़ेद", "off-white", "cream"),
    "brown": ("brown", "bhura", "bhoora", "भूरा", "भूरी"),
    "orange": ("orange", "narangi", "naarangi", "नारंगी", "kesari", "केसरी"),
    "purple": ("purple", "baingani", "jamuni", "बैंगनी", "जामुनी", "violet", "lavender"),
    "gold": ("gold", "golden", "sunehra", "sunehri", "सुनहरा", "सुनहरी", "zari"),
    "maroon": ("maroon", "मरून", "wine"),
    "grey": ("grey", "gray", "slaty", "स्लेटी"),
}

_LOOKUP: dict[str, str] = {
    normalise_devanagari(word.lower()): colour
    for colour, words in _COLOURS.items()
    for word in words
}
_WORD = re.compile(r"[A-Za-zऀ-ॿ]+(?:[- ](?:blue|white))?")


def colours_in(text: str) -> set[str]:
    found: set[str] = set()
    for match in _WORD.finditer(text):
        token = normalise_devanagari(match.group(0).lower())
        if token in _LOOKUP:
            found.add(_LOOKUP[token])
        else:
            for part in re.split(r"[- ]", token):
                if part in _LOOKUP:
                    found.add(_LOOKUP[part])
    # "light blue" / "sky blue" items should also match a plain "neela".
    if "sky" in found:
        found.add("blue")
    return found
