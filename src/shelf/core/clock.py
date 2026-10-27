"""Timestamps for API responses: always UTC with an explicit offset.

SQLite hands back naive datetimes (we store UTC), and a browser reads a naive ISO string as local
time, which shows Indian sellers times 5.5 hours off.
"""

from __future__ import annotations

from datetime import UTC, datetime


def iso_utc(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
