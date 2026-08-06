"""Persisted, review-oriented projection of a normalized job posting."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from .job import JobPosting


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

    def __post_init__(self) -> None:
        for field_name in ("job_id", "title", "company", "source", "url"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        if self.match is not None and not 0 <= self.match <= 1:
            raise ValueError("match must be between 0 and 1")

    @classmethod
    def from_job(
        cls,
        job: JobPosting,
        *,
        match: float | None = None,
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
