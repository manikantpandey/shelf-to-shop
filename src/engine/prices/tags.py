"""Prices read from printed signs and tags ("SUGAR 5KG @ 225/- ONLY", "20% OFF ON MRP").

Signs are full of numbers that are not prices: discounts, weights, pack counts and phone numbers.
Taking the first number turned "RICE 5Kg 20% OFF" into a ₹20 price. Here those are removed first,
and numbers marked as money (₹, Rs, @, /-, "only", "price") win over bare ones.
"""

from __future__ import annotations

import re

# Bump when the rules change, so cached runs re-read their sign prices.
TAG_PARSER_VERSION = 1
_DEVANAGARI = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER = r"\d+(?:[.,]\d+)*"
# Not prices: percentages, phone numbers, quantities with a unit, "2 for", "buy 2 get 1".
_NOISE = [
    re.compile(rf"{_NUMBER}\s*(?:%|percent\b|प्रतिशत)", re.IGNORECASE),
    re.compile(r"(?:\+?\d[\d\s-]{8,}\d)"),
    re.compile(
        rf"{_NUMBER}\s*(?:kg|kgs|g|gm|gms|gram|grams|mg|ml|l|ltr|ltrs|litre|litres|liter|liters|"
        r"pc|pcs|piece|pieces|pack|packs|x|n|nos|किलो|ग्राम|लीटर)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:buy|get)\s+\d+\b", re.IGNORECASE),
]
_CUED = [
    re.compile(rf"(?:₹|rs\.?|inr|@|price|only|now|रु\.?|रुपये)\s*({_NUMBER})", re.IGNORECASE),
    re.compile(rf"({_NUMBER})\s*(?:/-|/=|rs\b|rupees|₹|only|रुपये|रु\b)", re.IGNORECASE),
]
_MRP = re.compile(rf"m\.?\s*r\.?\s*p\.?\s*:?\s*(?:₹|rs\.?)?\s*({_NUMBER})", re.IGNORECASE)
_BARE = re.compile(rf"(?<![\d.,]){_NUMBER}(?![\d.,])")


def _value(raw: str) -> int | None:
    digits = raw.replace(",", "")
    try:
        value = float(digits)
    except ValueError:
        return None
    return round(value) if 0 < value < 10_000_000 else None


def _clean(text: str) -> str:
    text = text.translate(_DEVANAGARI)
    for noise in _NOISE:
        text = noise.sub(" ", text)
    return text


def tag_mrp(text: str | None) -> int | None:
    """The printed MRP on a tag, when it says so ("MRP 250")."""
    if not text:
        return None
    found = _MRP.search(text.translate(_DEVANAGARI))
    return _value(found.group(1)) if found else None


def tag_price(text: str | None, min_value: int = 2) -> int | None:
    """The selling price on a sign or tag, or None when no number on it is clearly a price."""
    if not text:
        return None
    mrp = tag_mrp(text)
    cleaned = _MRP.sub(" ", _clean(text))
    cued = [v for pattern in _CUED for m in pattern.finditer(cleaned) if (v := _value(m.group(1)))]
    cued = [v for v in cued if v >= min_value]
    if cued:
        return min(cued)
    bare = [v for m in _BARE.finditer(cleaned) if (v := _value(m.group(0))) and v >= 10]
    if len(set(bare)) == 1:
        return bare[0]
    if not bare and mrp is not None:
        # Only an MRP is printed: that is what the item sells for.
        return mrp
    return None
