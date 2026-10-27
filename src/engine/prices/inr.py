"""Indian rupee formatting. Money is stored as integer paise everywhere."""

from __future__ import annotations


def group_indian(n: int) -> str:
    """12345678 -> '1,23,45,678' (last three digits, then pairs)."""
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    if len(digits) <= 3:
        return sign + digits
    head, tail = digits[:-3], digits[-3:]
    pairs: list[str] = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    if head:
        pairs.insert(0, head)
    return sign + ",".join([*pairs, tail])


def format_inr(paise: int) -> str:
    """Display price: whole rupees drop the paise ('₹1,200'), others keep two places."""
    rupees, rem = divmod(abs(paise), 100)
    sign = "-" if paise < 0 else ""
    if rem == 0:
        return f"{sign}₹{group_indian(rupees)}"
    return f"{sign}₹{group_indian(rupees)}.{rem:02d}"


def feed_price(paise: int, currency: str = "INR") -> str:
    """Meta catalog feed price: number, space, ISO 4217 code, period decimal ('1200.00 INR')."""
    if paise < 0:
        raise ValueError("price cannot be negative")
    rupees, rem = divmod(paise, 100)
    return f"{rupees}.{rem:02d} {currency}"


def rupees_to_paise(rupees: int) -> int:
    return rupees * 100
