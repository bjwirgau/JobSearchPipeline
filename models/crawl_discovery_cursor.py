"""Persistent pagination state for external crawler indexes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class CrawlDiscoveryCursor:
    provider: str
    scope: str
    next_page: int
    page_count: int

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("discovery cursor provider must not be empty")
        if not self.scope.strip():
            raise ValueError("discovery cursor scope must not be empty")
        if self.page_count < 1:
            raise ValueError("discovery cursor page count must be positive")
        if not 0 <= self.next_page < self.page_count:
            raise ValueError(
                "discovery cursor next page must be within the page count"
            )

    @classmethod
    def from_row(cls, row: Mapping[str, object]) -> "CrawlDiscoveryCursor":
        return cls(
            provider=str(row["provider"]),
            scope=str(row["scope_key"]),
            next_page=int(row["next_page"]),
            page_count=int(row["page_count"]),
        )
