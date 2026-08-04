"""Lever public Postings API adapter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import quote

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LeverSite:
    company: str
    site: str
    api_base: str = "https://api.lever.co/v0/postings"


class LeverJobSource:
    name = "lever"

    def __init__(
        self,
        sites: tuple[LeverSite, ...],
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._sites = sites
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._sites)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        outcomes = await asyncio.gather(
            *(self._fetch_site(site) for site in self._sites),
            return_exceptions=True,
        )
        jobs: list[JobPosting] = []
        failures: list[BaseException] = []
        for site, outcome in zip(self._sites, outcomes):
            if isinstance(outcome, BaseException):
                LOGGER.warning("Lever site %s failed: %s", site.site, outcome)
                failures.append(outcome)
                continue
            jobs.extend(outcome)
        if not jobs and failures:
            raise RuntimeError(f"all Lever sites failed: {failures[0]}")
        return tuple(job for job in jobs if job_matches_query(job, query))[:limit]

    async def _fetch_site(self, site: LeverSite) -> tuple[JobPosting, ...]:
        url = f"{site.api_base.rstrip('/')}/{quote(site.site, safe='')}"
        response = await self._http.get(url, params={"mode": "json"})
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError(f"unexpected Lever response for {site.site}")
        normalized: list[JobPosting] = []
        for record in payload:
            if not isinstance(record, Mapping):
                continue
            categories = record.get("categories")
            categories = categories if isinstance(categories, Mapping) else {}
            salary = record.get("salaryRange")
            salary = salary if isinstance(salary, Mapping) else {}
            try:
                normalized.append(
                    self._normalizer.normalize(
                        source=self.name,
                        external_id=record.get("id"),
                        title=record.get("text"),
                        company=site.company,
                        url=record.get("hostedUrl") or record.get("applyUrl"),
                        location=categories.get("location", ""),
                        description=(
                            record.get("descriptionPlain")
                            or record.get("description")
                            or record.get("additionalPlain")
                            or ""
                        ),
                        employment_type=categories.get("commitment"),
                        salary_min=salary.get("min"),
                        salary_max=salary.get("max"),
                        salary_currency=salary.get("currency"),
                        posted_at=record.get("createdAt"),
                        raw=record,
                    )
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Lever job: %s", error)
        return tuple(normalized)
