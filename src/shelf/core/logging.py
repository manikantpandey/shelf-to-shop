"""Structured JSON logging with request ids and a scrubber for secrets and personal data."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "password",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "x-api-key",
        "login_code",
        "otp",
        "email",
        "phone",
        "whatsapp",
    }
)
REDACTED = "[redacted]"

_PATTERNS = [
    re.compile(r"\bLLM_[0-9]{6,}_[A-Za-z0-9._\-]+"),  # Meta Model API keys
    re.compile(r"\bsts_(?:live|test)_[a-z0-9]{8}\.[A-Za-z0-9_\-]+"),  # our API keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/=]+"),
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),  # email addresses
    re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)"),  # Indian mobile numbers
]


def scrub_text(value: str) -> str:
    for pattern in _PATTERNS:
        value = pattern.sub(REDACTED, value)
    return value


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return value
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {
            k: REDACTED if str(k).lower() in SENSITIVE_KEYS else _scrub(v, depth + 1)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [_scrub(v, depth + 1) for v in value]
    return value


def scrub_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """structlog processor: redact sensitive keys and secret-looking substrings."""
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = REDACTED
        else:
            event_dict[key] = _scrub(event_dict[key])
    return event_dict


def configure_logging(level: str = "INFO", *, json_output: bool = True) -> None:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.format_exc_info,
        scrub_processor,
    ]
    renderer: Any = (
        structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processor=renderer)
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's own access log would print raw query strings; we log requests ourselves.
    logging.getLogger("uvicorn.access").handlers[:] = []
    logging.getLogger("uvicorn.access").propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
