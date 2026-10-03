"""Normalize database timestamps; SQLite returns naive values for UTC columns."""
from datetime import datetime, timezone


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
