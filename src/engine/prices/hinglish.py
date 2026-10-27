"""Find spoken or written prices in Hinglish text, deterministically.

Handles digits ("1200", "1,200", "1.2k", "₹850", Devanagari digits), Hindi number words in Roman
and Devanagari script ("ek hazaar do sau", "बारह सौ"), English words ("twelve hundred"),
fractions ("saadhe aath sau" = 850, "dedh hazaar" = 1500, "paune do sau" = 175) and the colloquial
"barah pachaas" (= 1250). Each mention keeps its character span so it can be aligned to audio time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from engine.prices.numbers import (
    CURRENCY_WORDS,
    DEVANAGARI_DIGITS,
    FRACTIONS,
    JOINERS,
    MULTIPLIERS,
    NUMBER_WORDS,
    normalise_devanagari,
)

MAX_PRICE_INR = 10_000_000
# Bump when parsing changes, so cached pipeline runs re-read their transcripts.
PARSER_VERSION = 3
_TOKEN = re.compile(
    r"(?P<num>[0-9०-९](?:[0-9०-९]|,(?=[0-9०-९]))*(?:\.[0-9०-९]+)?(?:\s?[kK](?![A-Za-z]))?)"
    r"|(?P<word>[A-Za-zऀ-ॿ]+(?:-[A-Za-z]+)*\.?)"
    r"|(?P<rupee>₹)"
)
TokKind = Literal["num", "mult", "frac", "joiner", "currency", "other"]


@dataclass(frozen=True)
class _Tok:
    kind: TokKind
    start: int
    end: int
    value: float = 0.0
    frac: tuple[str, float] | None = None
    digits: bool = False


@dataclass(frozen=True)
class PriceMention:
    value: int  # rupees
    start: int  # character span in the original text
    end: int
    text: str
    source: Literal["digits", "words", "mixed"]
    colloquial: bool
    currency_cue: bool
    # A bare "hazaar"/"sau" right after an unknown word ("देव हजार") is usually a misheard
    # count ("dedh hazaar"), so the value is a guess.
    uncertain: bool = False

    @property
    def confidence(self) -> float:
        if self.uncertain:
            return 0.5
        if self.colloquial:
            return 0.6
        if self.currency_cue or self.source == "digits":
            return 0.95
        return 0.85


def _numeric_value(raw: str) -> float | None:
    text = raw.translate(DEVANAGARI_DIGITS).replace(",", "").replace(" ", "")
    scale = 1
    if text[-1:] in ("k", "K"):
        scale, text = 1000, text[:-1]
    try:
        return float(text) * scale
    except ValueError:
        return None


def _tokenise(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    for m in _TOKEN.finditer(text):
        start, end = m.span()
        if m.group("rupee"):
            tokens.append(_Tok("currency", start, end))
            continue
        if m.group("num"):
            value = _numeric_value(m.group("num"))
            kind: TokKind = "num" if value is not None else "other"
            tokens.append(_Tok(kind, start, end, value=value or 0.0, digits=True))
            continue
        word = normalise_devanagari(m.group("word").lower())
        bare = word.rstrip(".")
        if word in CURRENCY_WORDS or bare in CURRENCY_WORDS:
            tokens.append(_Tok("currency", start, end))
        elif bare in NUMBER_WORDS:
            tokens.append(_Tok("num", start, end, value=float(NUMBER_WORDS[bare])))
        elif bare in MULTIPLIERS:
            tokens.append(_Tok("mult", start, end, value=float(MULTIPLIERS[bare])))
        elif bare in FRACTIONS:
            tokens.append(_Tok("frac", start, end, frac=FRACTIONS[bare]))
        elif bare in JOINERS:
            tokens.append(_Tok("joiner", start, end))
        else:
            tokens.append(_Tok("other", start, end))
    return tokens


def _count(toks: list[_Tok], j: int) -> tuple[float, int] | None:
    """count := FRACTION? NUMBER | 'dedh' | 'dhai' | 'sava' (before a multiplier)."""
    if j >= len(toks):
        return None
    tok = toks[j]
    if tok.kind == "num":
        return tok.value, j + 1
    if tok.kind != "frac" or tok.frac is None:
        return None
    mode, amount = tok.frac
    if mode == "value":
        return amount, j + 1
    nxt = toks[j + 1] if j + 1 < len(toks) else None
    if nxt is not None and nxt.kind == "num" and not nxt.digits and nxt.value < 100:
        return nxt.value + amount, j + 2
    if mode == "sava":
        return 1 + amount, j + 1
    return None


def _parse_at(toks: list[_Tok], i: int) -> tuple[float, int, bool] | None:
    """Greedy Indian-system grammar: [count lakh] [count hazaar] [count sau] [units]."""
    total = 0.0
    j = i
    matched = False
    last_mult = float("inf")
    while j < len(toks):
        if matched and toks[j].kind == "joiner" and j + 1 < len(toks):
            if toks[j + 1].kind in ("num", "frac", "mult"):
                j += 1
                continue
            break
        counted = _count(toks, j)
        if counted is not None:
            cnt, k = counted
            nxt = toks[k] if k < len(toks) else None
            if nxt is not None and nxt.kind == "mult" and nxt.value < last_mult:
                total += cnt * nxt.value
                last_mult = nxt.value
                j = k + 1
                matched = True
                continue
            # A count before a multiplier that can't join this number starts the next price
            # ("do sau | teen sau"). Trailing units must be smaller than the last group.
            if nxt is not None and nxt.kind == "mult":
                break
            if matched and cnt >= last_mult:
                break
            # "barah barah rupaye" = 12 rupees each (Hindi repeats a number to mean "each").
            if (
                not matched
                and nxt is not None
                and nxt.kind == "num"
                and toks[j].kind == "num"
                and nxt.value == cnt
            ):
                return cnt, k + 1, False
            # "barah pachaas" = 12 x 100 + 50: a 1-99 number followed by a 10-99 number.
            colloquial = (
                not matched
                and nxt is not None
                and nxt.kind == "num"
                and toks[j].kind == "num"
                and nxt.digits == toks[j].digits
                and cnt.is_integer()
                and 1 <= cnt <= 99
                and nxt.value.is_integer()
                and 10 <= nxt.value <= 99
            )
            if colloquial and nxt is not None:
                return cnt * 100 + nxt.value, k + 1, True
            return total + cnt, k, False
        tok = toks[j]
        if tok.kind == "mult" and tok.value < last_mult:  # bare "sau" / "hazaar" means one
            total += tok.value
            last_mult = tok.value
            j += 1
            matched = True
            continue
        break
    return (total, j, False) if matched else None


def find_prices(text: str) -> list[PriceMention]:
    toks = _tokenise(text)
    mentions: list[PriceMention] = []
    i = 0
    while i < len(toks):
        if toks[i].kind not in ("num", "frac", "mult"):
            i += 1
            continue
        parsed = _parse_at(toks, i)
        if parsed is None:
            i += 1
            continue
        value, j, colloquial = parsed
        span = toks[i:j]
        if not value.is_integer() or not 1 <= value <= MAX_PRICE_INR:
            i = j
            continue
        before = toks[i - 1] if i > 0 else None
        after = toks[j] if j < len(toks) else None
        cue = any(t is not None and t.kind == "currency" for t in (before, after))
        if text[span[-1].end : span[-1].end + 2] == "/-":
            cue = True
        nums = [t for t in span if t.kind == "num"]
        if nums and all(t.digits for t in nums) and not any(t.kind == "mult" for t in span):
            source: Literal["digits", "words", "mixed"] = "digits"
        elif any(t.digits for t in nums):
            source = "mixed"
        else:
            source = "words"
        start, end = span[0].start, span[-1].end
        uncertain = span[0].kind == "mult" and before is not None and before.kind == "other"
        mentions.append(
            PriceMention(
                int(value), start, end, text[start:end], source, colloquial, cue, uncertain
            )
        )
        i = j
    return mentions


def likely_prices(mentions: list[PriceMention], min_value: int = 10) -> list[PriceMention]:
    """Drop small bare numbers ("do piece", "size 8") unless a currency word marks them as money."""
    return [m for m in mentions if m.value >= min_value or m.currency_cue]
