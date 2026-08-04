"""Credential-free remote job discovery through Remotive's public API."""

from __future__ import annotations

import asyncio
import logging
from typing import Mapping

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer, parse_salary

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)


class RemotiveJobSource:
    name = "remotive"
    API_URL = "https://remotive.com/api/remote-jobs"

    def __init__(self, *, http: HttpClient, normalizer: JobNormalizer) -> None:
        self._http = http
        self._normalizer = normalizer
        self._cache: tuple[JobPosting, ...] | None = None
        self._cache_lock = asyncio.Lock()

    def supports(self, criteria: SearchCriteria) -> bool:
        return True

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        jobs = await self._load_jobs()
        return tuple(job for job in jobs if job_matches_query(job, query))[:limit]

    async def _load_jobs(self) -> tuple[JobPosting, ...]:
        if self._cache is not None:
            return self._cache
        async with self._cache_lock:
            if self._cache is None:
                self._cache = await self._fetch_jobs()
        return self._cache

    async def _fetch_jobs(self) -> tuple[JobPosting, ...]:
        # One full-feed request can serve every role/location query in this run and
        # respects Remotive's guidance to avoid frequent API requests.
        response = await self._http.get(self.API_URL)
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
            raise ValueError("unexpected Remotive search response")

        jobs: list[JobPosting] = []
        for record in payload["jobs"]:
            if not isinstance(record, Mapping):
                continue
            salary_min, salary_max, currency = parse_salary(str(record.get("salary", "")))
            tags = record.get("tags")
            skills = tuple(str(value) for value in tags) if isinstance(tags, list) else ()
            category = str(record.get("category", "")).strip()
            try:
                job = self._normalizer.normalize(
                    source=self.name,
                    external_id=record.get("id"),
                    title=record.get("title"),
                    company=record.get("company_name") or "Unknown employer",
                    url=record.get("url"),
                    location=record.get("candidate_required_location", "Remote"),
                    description=record.get("description", ""),
                    skills=skills,
                    industries=(category,) if category else (),
                    employment_type=record.get("job_type"),
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=currency,
                    is_remote=True,
                    posted_at=record.get("publication_date"),
                    raw=record,
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Remotive job: %s", error)
                continue
            jobs.append(job)
        return tuple(jobs)
