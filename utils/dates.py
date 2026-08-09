"""Timezone-safe date helpers."""

from __future__ import annotations

import re
from datetime import datetime, timezone


MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MONTH_NUMBERS = {
    name.casefold(): index
    for index, name in enumerate(MONTH_NAMES, 1)
}
MONTH_NUMBERS.update(
    {name[:3].casefold(): index for index, name in enumerate(MONTH_NAMES, 1)}
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    return ensure_utc(value).isoformat() if value else None


def to_utc_naive(value: datetime) -> datetime:
    """Convert a timestamp for storage in a UTC MySQL DATETIME column."""

    return ensure_utc(value).replace(tzinfo=None)


def from_iso(value: str | None) -> datetime | None:
    return ensure_utc(datetime.fromisoformat(value)) if value else None


def format_month_year(value: str | None, *, allow_present: bool = False) -> str:
    """Render a resume date consistently without inventing missing month data."""

    if value is None:
        return ""
    cleaned = value.strip()
    if not cleaned:
        return ""
    if allow_present and cleaned.casefold() in {"present", "current"}:
        return "Present"

    iso_match = re.fullmatch(r"(\d{4})-(\d{2})(?:-(\d{2}))?", cleaned)
    if iso_match:
        year = int(iso_match.group(1))
        month = int(iso_match.group(2))
        if 1 <= month <= 12:
            day = int(iso_match.group(3) or "1")
            try:
                datetime(year, month, day)
            except ValueError:
                pass
            else:
                return f"{MONTH_NAMES[month - 1]} {year:04d}"

    parts = cleaned.split()
    if len(parts) == 2 and parts[0].casefold() in MONTH_NUMBERS:
        try:
            year = int(parts[1])
        except ValueError:
            pass
        else:
            month = MONTH_NUMBERS[parts[0].casefold()]
            if 1 <= year <= 9999:
                return f"{MONTH_NAMES[month - 1]} {year:04d}"

    expected = "YYYY-MM or Month YYYY"
    if allow_present:
        expected += ", or Present"
    raise ValueError(f"resume date must use {expected}: {value}")
