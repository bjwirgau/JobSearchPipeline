"""A company discovered through a public Greenhouse job board."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

from utils.dates import ensure_utc, to_iso
from utils.hashing import stable_hash


GREENHOUSE_BOARD_HOSTS = {
    "job-boards.greenhouse.io",
    "job-boards.eu.greenhouse.io",
}


@dataclass(frozen=True, slots=True)
class CompanyProspect:
    company_id: str
    company_name: str
    board_token: str
    company_url: str
    last_job_search_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("company_id", "company_name", "board_token", "company_url"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "board_token", self.board_token.casefold())
        parts = urlsplit(self.company_url)
        host = (parts.hostname or "").casefold()
        if parts.scheme != "https" or host not in GREENHOUSE_BOARD_HOSTS:
            raise ValueError("company_url must be a canonical Greenhouse board URL")
        for field_name in ("last_job_search_at", "created_at", "updated_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, ensure_utc(value))

    @classmethod
    def from_board(
        cls,
        *,
        company_name: str,
        board_token: str,
        company_url: str,
    ) -> "CompanyProspect":
        return cls(
            company_id=stable_hash("greenhouse", company_url),
            company_name=company_name,
            board_token=board_token,
            company_url=company_url,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CompanyProspect":
        return cls(
            company_id=str(row["company_id"]),
            company_name=str(row["company_name"]),
            board_token=str(row["board_token"]),
            company_url=str(row["company_url"]),
            last_job_search_at=_timestamp(row.get("last_job_search_at")),
            created_at=_timestamp(row.get("created_at")),
            updated_at=_timestamp(row.get("updated_at")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "board_token": self.board_token,
            "company_url": self.company_url,
            "last_job_search_at": to_iso(self.last_job_search_at),
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
        }


def _timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("company prospect timestamps must be datetime values")
    return ensure_utc(value)
