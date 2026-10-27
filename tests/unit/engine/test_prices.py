from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.prices.hinglish import find_prices, likely_prices
from engine.prices.inr import feed_price, format_inr, group_indian
from engine.prices.numbers import hindi_roman_word


def values(text: str) -> list[int]:
    return [m.value for m in find_prices(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ye neela wala 1200, cotton wala 850", [1200, 850]),
        ("ek hazaar do sau", [1200]),
        ("barah sau", [1200]),
        ("saadhe aath sau", [850]),
        ("dedh hazaar", [1500]),
        ("dhai sau", [250]),
        ("paune do sau", [175]),
        ("sava sau", [125]),
        ("sava do hazaar", [2250]),
        ("unnis sau ninyanve", [1999]),
        ("ek lakh bees hazaar", [120000]),
        ("ek hazaar aur do sau", [1200]),
        ("ek hazaar 200", [1200]),
        ("2 hazar", [2000]),
        ("12 sau", [1200]),
        ("do sau teen sau", [200, 300]),
        ("500 600", [500, 600]),
        ("Rs. 1,200/- only", [1200]),
        ("₹850", [850]),
        ("1.2k", [1200]),
        ("१२००", [1200]),
        ("बारह सौ रुपये", [1200]),
        ("एक हजार दो सौ", [1200]),
        ("एक हज़ार दो सौ", [1200]),  # nukta variant
        ("साढ़े तीन हज़ार", [3500]),
        ("पाँच सौ", [500]),
        ("पांच सौ", [500]),  # anusvara variant
        ("twelve hundred", [1200]),
        ("one thousand two hundred fifty", [1250]),
        ("twenty-five hundred", [2500]),
    ],
)
def test_find_prices(text: str, expected: list[int]) -> None:
    assert values(text) == expected


def test_colloquial_pairs_are_flagged() -> None:
    [m] = find_prices("ye wala barah pachaas")
    assert m.value == 1250
    assert m.colloquial
    assert m.confidence < 0.8
    [m] = find_prices("eight fifty")
    assert m.value == 850


def test_fraction_alone_is_not_a_price() -> None:
    assert find_prices("dedh") == []
    assert find_prices("saadhe aath baje") == []


def test_spans_point_at_the_original_text() -> None:
    text = "pehla 1200, doosra saadhe aath sau rupaye"
    mentions = find_prices(text)
    assert [text[m.start : m.end] for m in mentions] == ["1200", "saadhe aath sau"]
    assert mentions[1].currency_cue


def test_quantities_are_filtered_unless_marked_as_money() -> None:
    mentions = find_prices("do piece 500 ka, size 8 wali chappal 499, sirf 5 rupaye")
    assert [m.value for m in likely_prices(mentions)] == [500, 499, 5]


def test_ordinary_words_are_not_numbers() -> None:
    assert find_prices("no problem, so nice, sath mein le lo") == []


def _hinglish(n: int) -> str:
    parts = []
    lakhs, rest = divmod(n, 100_000)
    thousands, rest = divmod(rest, 1000)
    hundreds, units = divmod(rest, 100)
    if lakhs:
        parts += [hindi_roman_word(lakhs), "lakh"]
    if thousands:
        parts += [hindi_roman_word(thousands), "hazaar"]
    if hundreds:
        parts += [hindi_roman_word(hundreds), "sau"]
    if units:
        parts.append(hindi_roman_word(units))
    return " ".join(parts)


@given(st.integers(min_value=1, max_value=99_99_999))
def test_any_amount_in_hindi_words_parses_back(n: int) -> None:
    assert values(f"ye wala {_hinglish(n)} ka hai") == [n]


@given(st.integers(min_value=1, max_value=99_99_999))
def test_any_amount_in_indian_digit_grouping_parses_back(n: int) -> None:
    assert values(f"price {group_indian(n)} only") == [n]


@pytest.mark.parametrize(
    ("n", "grouped"),
    [(0, "0"), (999, "999"), (1000, "1,000"), (120000, "1,20,000"), (12345678, "1,23,45,678")],
)
def test_group_indian(n: int, grouped: str) -> None:
    assert group_indian(n) == grouped


def test_format_inr_and_feed_price() -> None:
    assert format_inr(120000_00) == "₹1,20,000"
    assert format_inr(85050) == "₹850.50"
    assert feed_price(120000) == "1200.00 INR"
    with pytest.raises(ValueError):
        feed_price(-1)
