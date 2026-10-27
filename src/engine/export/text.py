"""Clean model-written product text before it reaches a customer or the Meta feed."""

from __future__ import annotations

import re
import unicodedata

_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b\S+\.(?:com|in|net|org|io|co|shop|me)\b\S*")
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s\-]?){9,13}\d(?!\d)")
_TAG = re.compile(r"<[^>]{0,200}>")
_SPACE = re.compile(r"\s+")


def clean_text(text: str, max_len: int | None = None) -> str:
    """Plain text: no HTML, links, emails, phone numbers or control characters."""
    text = unicodedata.normalize("NFC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    for pattern in (_TAG, _URL, _EMAIL, _PHONE):
        text = pattern.sub(" ", text)
    text = _SPACE.sub(" ", text).strip(" ,;:-")
    if max_len is not None and len(text) > max_len:
        cut = text[: max_len - 1].rsplit(" ", 1)[0]
        text = cut.rstrip(" ,;:-") + "…"
    return text


def is_shouting(text: str) -> bool:
    letters = [c for c in text if c.isalpha() and c.isascii()]
    return len(letters) >= 10 and all(c.isupper() for c in letters)
