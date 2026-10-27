"""Prices read from signs: discounts, weights and phone numbers are never prices."""

from __future__ import annotations

import pytest

from engine.prices.tags import tag_mrp, tag_price


@pytest.mark.parametrize(
    ("text", "price"),
    [
        ("DAAWAT BASMATI RICE 5Kg 20% OFF ON MRP", None),  # a discount, not a price
        ("DHAMPURE, MADHUR SUGAR 5KG @ 225/- ONLY", 225),
        ("Call 9999076864", None),
        ("Call +91 99990 76864", None),
        ("₹45", 45),
        ("Rs. 120", 120),
        ("Rs 1,250/-", 1250),
        ("MRP 250 Our price 225", 225),
        ("MRP ₹60", 60),
        ("Maggi 12", 12),
        ("1 kg 60", 60),
        ("Buy 2 get 1 free", None),
        ("50% off", None),
        ("2 for 25 rupees", 25),
        ("चीनी ५ किलो ₹२२५", 225),
        ("500 ml 40/-", 40),
        ("Pack of 6 120 only", 120),
        ("New arrival", None),
        ("", None),
        (None, None),
    ],
)
def test_tag_price(text: str | None, price: int | None) -> None:
    assert tag_price(text) == price


def test_tag_mrp() -> None:
    assert tag_mrp("MRP 250 Our price 225") == 250
    assert tag_mrp("M.R.P. Rs 99") == 99
    assert tag_mrp("@ 225/-") is None
