"""Authorized LinkedIn integration boundary without scraping or login automation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Mapping, Protocol

from models import JobPosting, SearchCriteria, SearchQuery
from services.job_normalization_service import JobNormalizer


class AuthorizedLinkedInClient(Protocol):
    """Client supplied only after LinkedIn partner/API approval."""

    async def search_jobs(
        self,
        query: SearchQuery,
        *,
        limit: int,
    ) -> Sequence[Mapping[str, Any]]:
        """Return authorized LinkedIn job records."""


class LinkedInJobSource:
    name = "linkedin"

    def __init__(
        self,
        client: AuthorizedLinkedInClient,
        *,
        normalizer: JobNormalizer,
    ) -> None:
        self._client = client
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        return True

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        records = await self._client.search_jobs(query, limit=limit)
        jobs: list[JobPosting] = []
        for record in records:
            raw_skills = record.get("skills", ())
            if isinstance(raw_skills, str):
                skills = tuple(
                    value.strip() for value in raw_skills.split(",") if value.strip()
                )
            else:
                skills = tuple(raw_skills)
            jobs.append(
                self._normalizer.normalize(
                    source=self.name,
                    external_id=record.get("id") or record.get("jobPostingId"),
                    title=record.get("title"),
                    company=record.get("company") or record.get("companyName"),
                    url=record.get("url") or record.get("jobPostingUrl"),
                    location=record.get("location", ""),
                    description=record.get("description", ""),
                    skills=skills,
                    employment_type=record.get("employmentType"),
                    salary_min=record.get("salaryMin"),
                    salary_max=record.get("salaryMax"),
                    salary_currency=record.get("salaryCurrency"),
                    is_remote=record.get("isRemote"),
                    posted_at=record.get("listedAt") or record.get("datePosted"),
                    raw=record,
                )
            )
        return tuple(jobs)[:limit]
