"""WhatsApp click-to-chat links (https://wa.me/<number>?text=<urlencoded message>)."""

from __future__ import annotations

import re
from urllib.parse import quote

from engine.prices.inr import format_inr

_DIGITS = re.compile(r"\D")

ORDER_MESSAGES = {
    "en": "Hello {shop}, I want to order: {title} ({price}). {url}",
    "hi": "नमस्ते {shop}, मुझे यह चाहिए: {title} ({price}). {url}",
}


class InvalidWhatsAppNumberError(ValueError):
    pass


def normalise_number(raw: str, default_country: str = "91") -> str:
    """Full international number as digits only: no '+', zeros, brackets or dashes."""
    digits = _DIGITS.sub("", raw)
    if raw.strip().startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]  # trunk prefix, e.g. 09876543210
    if len(digits) == 10 and default_country == "91":
        if digits[0] not in "6789":
            raise InvalidWhatsAppNumberError("Indian mobile numbers start with 6, 7, 8 or 9")
        digits = "91" + digits
    if not 11 <= len(digits) <= 15:
        raise InvalidWhatsAppNumberError("enter the full mobile number with country code")
    return digits


def order_message(shop: str, title: str, price_paise: int, url: str, lang: str = "en") -> str:
    template = ORDER_MESSAGES.get(lang, ORDER_MESSAGES["en"])
    return template.format(shop=shop, title=title, price=format_inr(price_paise), url=url)


def order_link(number: str, message: str) -> str:
    return f"https://wa.me/{normalise_number(number)}?text={quote(message, safe='')}"
