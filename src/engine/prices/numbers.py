"""Number vocabulary for Hindi (Roman and Devanagari script) and English."""

from __future__ import annotations

import unicodedata

# Hindi 1-99 in Roman script, with common spelling variants. "no", "so" and "sath" are left out:
# they are everyday English/Hindi words far more often than numbers.
_HINDI_ROMAN: dict[int, tuple[str, ...]] = {
    1: ("ek", "ik"),
    2: ("do", "doo"),
    3: ("teen", "tin"),
    4: ("char", "chaar", "chār"),
    5: ("paanch", "panch", "paach", "panc"),
    6: ("chhe", "chhah", "chhai", "che", "chah", "chheh", "chha"),
    7: ("saat", "sat"),
    8: ("aath", "ath", "aat"),
    9: ("nau",),
    10: ("das", "dus"),
    11: ("gyarah", "gyara", "gyaarah", "gyaara"),
    12: ("barah", "bara", "baarah", "baara"),
    13: ("terah", "tera"),
    14: ("chaudah", "chauda", "chodah", "choda"),
    15: ("pandrah", "pandra", "pundrah", "pandhra"),
    16: ("solah", "sola"),
    17: ("satrah", "satra", "sattrah", "sattra"),
    18: ("atharah", "athara", "attharah", "atthara", "athaarah"),
    19: ("unnees", "unnis", "unis", "unees"),
    20: ("bees", "bis"),
    21: ("ikkees", "ikkis"),
    22: ("baees", "bais", "baais", "baaees"),
    23: ("teyees", "teis", "teyis", "teees"),
    24: ("chaubees", "chaubis", "chobis", "chaubis"),
    25: ("pachchees", "pachees", "pachis", "pacchis", "pachchis"),
    26: ("chhabbees", "chabbis", "chhabbis", "chabbees"),
    27: ("sattaees", "sattais", "satais", "sattaais"),
    28: ("atthaees", "atthais", "athais", "athaais"),
    29: ("untees", "untis"),
    30: ("tees", "tis"),
    31: ("ikattees", "iktis", "ikattis", "ikatis"),
    32: ("battees", "battis"),
    33: ("taintees", "taintis", "tetis", "taitis"),
    34: ("chauntees", "chautis", "chontis", "chauntis"),
    35: ("paintees", "paintis", "pentis"),
    36: ("chhattees", "chhattis", "chattis"),
    37: ("saintees", "saintis", "sentis"),
    38: ("artees", "adtis", "artis", "adhtis", "adtees"),
    39: ("untaalees", "untalis", "untaalis"),
    40: ("chaalees", "chalis", "chaalis"),
    41: ("iktaalees", "iktalis", "iktaalis"),
    42: ("bayaalees", "bayalis", "byalis", "bayaalis"),
    43: ("taintaalees", "taintalis", "tetalis"),
    44: ("chavaalees", "chawalis", "chauvalis", "chavalis"),
    45: ("paintaalees", "paintalis", "pentalis"),
    46: ("chhiyaalees", "chhiyalis", "chiyalis"),
    47: ("saintaalees", "saintalis", "sentalis"),
    48: ("artaalees", "artalis", "adtalis", "adtaalis"),
    49: ("unchaas", "unchas"),
    50: ("pachaas", "pachas", "pachaass"),
    51: ("ikyaavan", "ikyavan", "ikyawan"),
    52: ("baavan", "bavan", "bawan"),
    53: ("tirpan", "trepan", "tirepan"),
    54: ("chauvan", "chauwan", "chovan"),
    55: ("pachpan",),
    56: ("chhappan", "chappan"),
    57: ("sattaavan", "sattavan", "sattawan"),
    58: ("atthaavan", "atthavan", "athavan"),
    59: ("unsath", "unsaath"),
    60: ("saath",),
    61: ("iksath", "iksaath"),
    62: ("baasath", "basath"),
    63: ("tirsath", "tresath"),
    64: ("chaunsath", "chausath"),
    65: ("painsath", "pensath"),
    66: ("chhiyaasath", "chhiyasath", "chiyasath"),
    67: ("sadsath", "sarsath"),
    68: ("adsath", "arsath"),
    69: ("unhattar",),
    70: ("sattar",),
    71: ("ikhattar",),
    72: ("bahattar",),
    73: ("tihattar",),
    74: ("chauhattar",),
    75: ("pachhattar", "pachattar"),
    76: ("chhihattar", "chihattar"),
    77: ("satattar", "sathattar", "satahattar"),
    78: ("athattar", "athhattar"),
    79: ("unaasi", "unasi"),
    80: ("assi", "assee"),
    81: ("ikyaasi", "ikyasi"),
    82: ("bayaasi", "bayasi"),
    83: ("tiraasi", "tirasi"),
    84: ("chauraasi", "chaurasi"),
    85: ("pachaasi", "pachasi"),
    86: ("chhiyaasi", "chhiyasi"),
    87: ("sataasi", "satasi", "sattasi"),
    88: ("athaasi", "athasi", "atthasi"),
    89: ("navaasi", "navasi"),
    90: ("nabbe", "nabbey"),
    91: ("ikyaanave", "ikyanave", "ikyanve"),
    92: ("baanave", "banave", "banve"),
    93: ("tiraanave", "tiranave", "tiranve"),
    94: ("chauraanave", "chauranave", "chauranve"),
    95: ("pachaanave", "pachanave", "pachanve"),
    96: ("chhiyaanave", "chhiyanave", "chhiyanve"),
    97: ("sattaanave", "sattanave", "sattanve"),
    98: ("atthaanave", "atthanave", "atthanve"),
    99: ("ninyaanave", "ninyanave", "ninyanve", "ninyaanve"),
}

_HINDI_DEVANAGARI: dict[int, tuple[str, ...]] = {
    1: ("एक",), 2: ("दो",), 3: ("तीन",), 4: ("चार",), 5: ("पाँच", "पांच"),
    6: ("छह", "छः", "छे", "छै"), 7: ("सात",), 8: ("आठ",), 9: ("नौ",), 10: ("दस",),
    11: ("ग्यारह",), 12: ("बारह",), 13: ("तेरह",), 14: ("चौदह",), 15: ("पंद्रह", "पन्द्रह"),
    16: ("सोलह",), 17: ("सत्रह",), 18: ("अठारह",), 19: ("उन्नीस",), 20: ("बीस",),
    21: ("इक्कीस",), 22: ("बाईस",), 23: ("तेईस",), 24: ("चौबीस",), 25: ("पच्चीस",),
    26: ("छब्बीस",), 27: ("सत्ताईस",), 28: ("अट्ठाईस",), 29: ("उनतीस",), 30: ("तीस",),
    31: ("इकतीस",), 32: ("बत्तीस",), 33: ("तैंतीस",), 34: ("चौंतीस",), 35: ("पैंतीस",),
    36: ("छत्तीस",), 37: ("सैंतीस",), 38: ("अड़तीस",), 39: ("उनतालीस",), 40: ("चालीस",),
    41: ("इकतालीस",), 42: ("बयालीस",), 43: ("तैंतालीस",), 44: ("चवालीस", "चौवालीस"),
    45: ("पैंतालीस",), 46: ("छियालीस",), 47: ("सैंतालीस",), 48: ("अड़तालीस",),
    49: ("उनचास",), 50: ("पचास",), 51: ("इक्यावन",), 52: ("बावन",), 53: ("तिरपन",),
    54: ("चौवन",), 55: ("पचपन",), 56: ("छप्पन",), 57: ("सत्तावन",), 58: ("अट्ठावन",),
    59: ("उनसठ",), 60: ("साठ",), 61: ("इकसठ",), 62: ("बासठ",), 63: ("तिरसठ",),
    64: ("चौंसठ",), 65: ("पैंसठ",), 66: ("छियासठ",), 67: ("सड़सठ",), 68: ("अड़सठ",),
    69: ("उनहत्तर",), 70: ("सत्तर",), 71: ("इकहत्तर",), 72: ("बहत्तर",), 73: ("तिहत्तर",),
    74: ("चौहत्तर",), 75: ("पचहत्तर",), 76: ("छिहत्तर",), 77: ("सतहत्तर",), 78: ("अठहत्तर",),
    79: ("उन्यासी", "उनासी"), 80: ("अस्सी",), 81: ("इक्यासी",), 82: ("बयासी",), 83: ("तिरासी",),
    84: ("चौरासी",), 85: ("पचासी",), 86: ("छियासी",), 87: ("सत्तासी",), 88: ("अट्ठासी",),
    89: ("नवासी",), 90: ("नब्बे",), 91: ("इक्यानवे",), 92: ("बानवे",), 93: ("तिरानवे",),
    94: ("चौरानवे",), 95: ("पचानवे",), 96: ("छियानवे",), 97: ("सत्तानवे",), 98: ("अट्ठानवे",),
    99: ("निन्यानवे",),
}  # fmt: skip

_ENGLISH_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_ENGLISH_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip

MULTIPLIERS: dict[str, int] = {
    **dict.fromkeys(("sau", "sou", "hundred", "सौ"), 100),
    **dict.fromkeys(
        ("hazaar", "hazar", "hajar", "hajaar", "hazzar", "thousand", "हजार", "हज़ार"), 1000
    ),
    **dict.fromkeys(("lakh", "lac", "laakh", "lakhs", "लाख"), 100_000),
}

# Fraction words. "plus": added to the count that follows ("saadhe aath sau" = 8.5 x 100).
# "value": the whole count ("dedh hazaar" = 1.5 x 1000). "sava" works both ways.
FRACTIONS: dict[str, tuple[str, float]] = {
    # "सादे"/"साडे" are common ASR spellings of साढ़े; a fraction only counts before a number.
    **dict.fromkeys(
        ("saadhe", "sade", "saade", "sadhe", "saadhey", "साढ़े", "साढे", "सादे", "साडे"), ("plus", 0.5)
    ),
    **dict.fromkeys(("paune", "pone", "paun", "पौने"), ("plus", -0.25)),
    **dict.fromkeys(("sava", "savaa", "sawa", "sawaa", "सवा"), ("sava", 0.25)),
    **dict.fromkeys(("dedh", "derh", "dedhh", "डेढ़", "डेढ"), ("value", 1.5)),
    **dict.fromkeys(("dhai", "dhaai", "adhai", "adhaai", "ढाई"), ("value", 2.5)),
}

CURRENCY_WORDS = frozenset(
    {"rs", "rs.", "inr", "rupees", "rupee", "rupaye", "rupaiye", "rupiya", "rupiye", "₹",
     "रुपये", "रुपए", "रुपया", "rupay"}
)  # fmt: skip
JOINERS = frozenset({"aur", "and", "और"})


def normalise_devanagari(text: str) -> str:
    """Fold nukta and chandrabindu so spelling variants of a word compare equal."""
    text = unicodedata.normalize("NFC", text)
    decomposed = unicodedata.normalize("NFD", text).replace("़", "")
    return unicodedata.normalize("NFC", decomposed).replace("ँ", "ं")


def _build_words() -> dict[str, int]:
    words: dict[str, int] = {}
    for value, spellings in _HINDI_ROMAN.items():
        for s in spellings:
            words[s] = value
    for value, spellings in _HINDI_DEVANAGARI.items():
        for s in spellings:
            words[normalise_devanagari(s)] = value
    for value, word in enumerate(_ENGLISH_UNITS):
        words[word] = value
    for tens_word, tens in _ENGLISH_TENS.items():
        words[tens_word] = tens
        for unit in range(1, 10):
            words[f"{tens_word}-{_ENGLISH_UNITS[unit]}"] = tens + unit
    return words


NUMBER_WORDS: dict[str, int] = _build_words()
MULTIPLIERS = {normalise_devanagari(k): v for k, v in MULTIPLIERS.items()}
FRACTIONS = {normalise_devanagari(k): v for k, v in FRACTIONS.items()}
CURRENCY_WORDS = frozenset(normalise_devanagari(w) for w in CURRENCY_WORDS)

DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def hindi_roman_word(value: int) -> str:
    """Canonical Roman-script Hindi word for 1-99 (used by tests to generate phrases)."""
    return _HINDI_ROMAN[value][0]
