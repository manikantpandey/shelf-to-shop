"""Timestamps for API responses: always UTC with an explicit offset.

SQLite hands back naive datetimes (we store UTC), and a browser reads a naive ISO string as local
time, which shows Indian sellers times 5.5 hours off.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def iso_utc(value: datetime) -> str:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def india_today() -> date:
    """Days roll over at midnight in India, where the shops are."""
    return datetime.now(IST).date()
