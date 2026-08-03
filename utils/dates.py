"""Timezone-safe date helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    return ensure_utc(value).isoformat() if value else None


def from_iso(value: str | None) -> datetime | None:
    return ensure_utc(datetime.fromisoformat(value)) if value else None
