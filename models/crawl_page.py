"""Persistent crawl eligibility and outcome for one public page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping
from urllib.parse import urlsplit

from utils.dates import ensure_utc, to_iso


class CrawlPageType(StrEnum):
    COMPANY_BOARD = "company_board"


class CrawlStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CrawlPage:
    page_url: str
    source: str
    page_type: CrawlPageType
    crawl_status: CrawlStatus
    last_crawled_at: datetime
    next_crawl_at: datetime
    last_error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("page_url", "source"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        parts = urlsplit(self.page_url)
        if parts.scheme != "https" or not parts.hostname:
            raise ValueError("page_url must be an absolute HTTPS URL")
        object.__setattr__(self, "source", self.source.casefold())
        object.__setattr__(self, "page_type", CrawlPageType(self.page_type))
        object.__setattr__(self, "crawl_status", CrawlStatus(self.crawl_status))
        for field_name in (
            "last_crawled_at",
            "next_crawl_at",
            "created_at",
            "updated_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, ensure_utc(value))
        if self.next_crawl_at < self.last_crawled_at:
            raise ValueError("next_crawl_at must not precede last_crawled_at")
        if self.last_error is not None:
            error = self.last_error.strip() or None
            if error is not None and len(error) > 1_024:
                raise ValueError("last_error must not exceed 1024 characters")
            object.__setattr__(self, "last_error", error)

    @classmethod
    def from_attempt(
        cls,
        *,
        page_url: str,
        source: str,
        page_type: CrawlPageType,
        crawl_status: CrawlStatus,
        crawled_at: datetime,
        revisit_after: timedelta,
        last_error: str | None = None,
    ) -> "CrawlPage":
        if revisit_after.total_seconds() <= 0:
            raise ValueError("revisit_after must be greater than zero")
        crawled_at = ensure_utc(crawled_at)
        return cls(
            page_url=page_url,
            source=source,
            page_type=page_type,
            crawl_status=crawl_status,
            last_crawled_at=crawled_at,
            next_crawl_at=crawled_at + revisit_after,
            last_error=(last_error or "")[:1_024] or None,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CrawlPage":
        return cls(
            page_url=str(row["page_url"]),
            source=str(row["source"]),
            page_type=CrawlPageType(str(row["page_type"])),
            crawl_status=CrawlStatus(str(row["crawl_status"])),
            last_crawled_at=_timestamp(row["last_crawled_at"]),
            next_crawl_at=_timestamp(row["next_crawl_at"]),
            last_error=(str(row["last_error"]) if row.get("last_error") else None),
            created_at=_optional_timestamp(row.get("created_at")),
            updated_at=_optional_timestamp(row.get("updated_at")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "page_url": self.page_url,
            "source": self.source,
            "page_type": self.page_type.value,
            "crawl_status": self.crawl_status.value,
            "last_crawled_at": to_iso(self.last_crawled_at),
            "next_crawl_at": to_iso(self.next_crawl_at),
            "last_error": self.last_error,
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
        }


def _timestamp(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("crawl-page timestamps must be datetime values")
    return ensure_utc(value)


def _optional_timestamp(value: object) -> datetime | None:
    return _timestamp(value) if value is not None else None
