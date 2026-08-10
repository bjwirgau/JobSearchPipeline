"""Persisted, review-oriented projection of a normalized job posting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping

from utils.dates import ensure_utc, to_iso

from .job import JobPosting


DEFAULT_RESUME_CANDIDATE_THRESHOLD = 0.85
DEFAULT_RESUME_GENERATION_MODEL = "gpt-5.4"


@dataclass(frozen=True, slots=True)
class JobProspect:
    job_id: str
    match: float | None
    title: str
    company: str
    location: str
    salary: str
    source: str
    url: str
    posted_at: datetime | None = None
    resume_generation_checked: bool = False
    resume_generation_candidate: bool = False
    resume_generation_model: str | None = None
    resume_file_name: str | None = None
    cover_letter_file_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("job_id", "title", "company", "source", "url"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        if self.match is not None and not 0 <= self.match <= 1:
            raise ValueError("match must be between 0 and 1")
        if self.resume_generation_model is not None:
            model = self.resume_generation_model.strip()
            if not model:
                raise ValueError("resume_generation_model must not be empty")
            object.__setattr__(self, "resume_generation_model", model)
        for field_name in ("resume_file_name", "cover_letter_file_name"):
            value = getattr(self, field_name)
            if value is not None:
                file_name = value.strip()
                if not file_name:
                    raise ValueError(f"{field_name} must not be empty")
                object.__setattr__(self, field_name, file_name)
        if self.resume_generation_candidate and self.resume_generation_model is None:
            raise ValueError(
                "resume_generation_model is required for a resume candidate"
            )
        for field_name in ("posted_at", "created_at", "updated_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, ensure_utc(value))

    @classmethod
    def from_job(
        cls,
        job: JobPosting,
        *,
        match: float | None = None,
        resume_generation_checked: bool = False,
        resume_generation_candidate: bool = False,
        resume_generation_model: str | None = None,
    ) -> "JobProspect":
        return cls(
            job_id=job.job_id,
            match=match,
            title=job.title,
            company=job.company,
            location=job.location or "Not provided",
            salary=_format_salary(job),
            source=job.source,
            url=job.url,
            posted_at=job.posted_at,
            resume_generation_checked=resume_generation_checked,
            resume_generation_candidate=resume_generation_candidate,
            resume_generation_model=resume_generation_model,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "JobProspect":
        raw_match = row.get("match")
        return cls(
            job_id=str(row["job_id"]),
            match=(
                float(raw_match)
                if isinstance(raw_match, (int, float, Decimal))
                else None
            ),
            title=str(row["title"]),
            company=str(row["company"]),
            location=str(row["location"]),
            salary=str(row["salary"]),
            source=str(row["source"]),
            url=str(row["url"]),
            posted_at=_timestamp(row.get("posted_at")),
            resume_generation_checked=bool(
                row.get("resume_generation_checked", False)
            ),
            resume_generation_candidate=bool(
                row.get("resume_generation_candidate", False)
            ),
            resume_generation_model=(
                str(row["resume_generation_model"])
                if row.get("resume_generation_model") is not None
                else None
            ),
            resume_file_name=(
                str(row["resume_file_name"])
                if row.get("resume_file_name") is not None
                else None
            ),
            cover_letter_file_name=(
                str(row["cover_letter_file_name"])
                if row.get("cover_letter_file_name") is not None
                else None
            ),
            created_at=_timestamp(row.get("created_at")),
            updated_at=_timestamp(row.get("updated_at")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "match": self.match,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "salary": self.salary,
            "source": self.source,
            "url": self.url,
            "posted_at": to_iso(self.posted_at),
            "resume_generation_checked": self.resume_generation_checked,
            "resume_generation_candidate": self.resume_generation_candidate,
            "resume_generation_model": self.resume_generation_model,
            "resume_file_name": self.resume_file_name,
            "cover_letter_file_name": self.cover_letter_file_name,
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
        }


def _format_salary(job: JobPosting) -> str:
    if job.salary_min is None and job.salary_max is None:
        return "Not provided"
    minimum = f"{job.salary_min:,}" if job.salary_min is not None else ""
    maximum = f"{job.salary_max:,}" if job.salary_max is not None else ""
    amount = (
        minimum
        if minimum == maximum or not maximum
        else maximum
        if not minimum
        else f"{minimum}-{maximum}"
    )
    return f"{job.salary_currency} {amount}" if job.salary_currency else amount


def _timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError("job prospect timestamps must be datetime values")
    return ensure_utc(value)
