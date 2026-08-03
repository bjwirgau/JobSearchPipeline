"""Normalized job postings and search request models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from utils.dates import from_iso, to_iso, utc_now
from utils.hashing import stable_hash


def _clean(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(value.strip() for value in values if value.strip())


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    job_titles: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    remote_only: bool = False
    employment_types: tuple[str, ...] = ()
    minimum_salary: int | None = None
    excluded_keywords: tuple[str, ...] = ()
    max_age_days: int | None = 30
    source_names: tuple[str, ...] = ()
    results_per_query: int = 50

    def __post_init__(self) -> None:
        for field_name in (
            "job_titles",
            "skills",
            "locations",
            "employment_types",
            "excluded_keywords",
            "source_names",
        ):
            object.__setattr__(self, field_name, _clean(getattr(self, field_name)))
        if not self.job_titles and not self.skills:
            raise ValueError("at least one job title or skill is required")
        if self.minimum_salary is not None and self.minimum_salary < 0:
            raise ValueError("minimum_salary must not be negative")
        if self.max_age_days is not None and self.max_age_days < 0:
            raise ValueError("max_age_days must not be negative")
        if self.results_per_query <= 0:
            raise ValueError("results_per_query must be greater than zero")


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    title: str | None = None
    skills: tuple[str, ...] = ()
    location: str | None = None
    remote_only: bool = False


@dataclass(frozen=True, slots=True)
class JobPosting:
    source: str
    external_id: str
    title: str
    company: str
    url: str
    job_id: str = ""
    location: str = ""
    description: str = ""
    skills: tuple[str, ...] = ()
    responsibilities: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    is_remote: bool | None = None
    posted_at: datetime | None = None
    discovered_at: datetime = field(default_factory=utc_now)
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        for field_name in ("source", "external_id", "title", "company", "url"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        if not self.job_id:
            object.__setattr__(
                self,
                "job_id",
                stable_hash(self.source, self.external_id),
            )
        for field_name in ("skills", "responsibilities", "requirements"):
            object.__setattr__(self, field_name, _clean(getattr(self, field_name)))
        if self.salary_min is not None and self.salary_min < 0:
            raise ValueError("salary_min must not be negative")
        if self.salary_max is not None and self.salary_max < 0:
            raise ValueError("salary_max must not be negative")
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_max < self.salary_min
        ):
            raise ValueError("salary_max must be greater than or equal to salary_min")

    @property
    def deduplication_key(self) -> str:
        return stable_hash(self.company, self.title, self.location)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source": self.source,
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "location": self.location,
            "description": self.description,
            "skills": list(self.skills),
            "responsibilities": list(self.responsibilities),
            "requirements": list(self.requirements),
            "employment_type": self.employment_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "salary_currency": self.salary_currency,
            "is_remote": self.is_remote,
            "posted_at": to_iso(self.posted_at),
            "discovered_at": to_iso(self.discovered_at),
            "raw": dict(self.raw),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "JobPosting":
        return cls(
            job_id=str(value.get("job_id", "")),
            source=str(value["source"]),
            external_id=str(value["external_id"]),
            title=str(value["title"]),
            company=str(value["company"]),
            url=str(value["url"]),
            location=str(value.get("location", "")),
            description=str(value.get("description", "")),
            skills=tuple(value.get("skills", ())),
            responsibilities=tuple(value.get("responsibilities", ())),
            requirements=tuple(value.get("requirements", ())),
            employment_type=value.get("employment_type"),
            salary_min=value.get("salary_min"),
            salary_max=value.get("salary_max"),
            salary_currency=value.get("salary_currency"),
            is_remote=value.get("is_remote"),
            posted_at=from_iso(value.get("posted_at")),
            discovered_at=from_iso(value.get("discovered_at")) or utc_now(),
            raw=value.get("raw", {}),
        )


@dataclass(frozen=True, slots=True)
class SearchFailure:
    source: str
    query: SearchQuery
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class SearchRunResult:
    queries: tuple[SearchQuery, ...]
    selected_sources: tuple[str, ...]
    fetched_count: int
    eligible_count: int
    deduplicated_count: int
    stored_count: int
    jobs: tuple[JobPosting, ...]
    failures: tuple[SearchFailure, ...] = ()
