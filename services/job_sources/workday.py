"""Configurable Workday public-career-site CXS adapter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urljoin

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WorkdayTenant:
    company: str
    cxs_url: str


class WorkdayJobSource:
    """Use tenant-specific public CXS endpoints; response shapes can vary by tenant."""

    name = "workday"

    def __init__(
        self,
        tenants: tuple[WorkdayTenant, ...],
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._tenants = tenants
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._tenants)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        outcomes = await asyncio.gather(
            *(self._search_tenant(tenant, query, limit) for tenant in self._tenants),
            return_exceptions=True,
        )
        jobs: list[JobPosting] = []
        failures: list[BaseException] = []
        for tenant, outcome in zip(self._tenants, outcomes):
            if isinstance(outcome, BaseException):
                LOGGER.warning("Workday tenant %s failed: %s", tenant.cxs_url, outcome)
                failures.append(outcome)
                continue
            jobs.extend(outcome)
        if not jobs and failures:
            raise RuntimeError(f"all Workday tenants failed: {failures[0]}")
        return tuple(jobs)[:limit]

    async def _search_tenant(
        self,
        tenant: WorkdayTenant,
        query: SearchQuery,
        limit: int,
    ) -> tuple[JobPosting, ...]:
        base = tenant.cxs_url.rstrip("/")
        response = await self._http.post_json(
            f"{base}/jobs",
            {
                "appliedFacets": {},
                "limit": limit,
                "offset": 0,
                "searchText": query.text,
            },
        )
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(
            payload.get("jobPostings"), list
        ):
            raise ValueError(f"unexpected Workday response for {tenant.cxs_url}")

        preliminary = []
        for record in payload["jobPostings"]:
            if not isinstance(record, Mapping):
                continue
            external_path = str(record.get("externalPath", ""))
            public_url = urljoin(tenant.cxs_url, external_path)
            bullet_fields = record.get("bulletFields")
            listing_id = (
                bullet_fields[-1]
                if isinstance(bullet_fields, list) and bullet_fields
                else external_path
            )
            try:
                job = self._normalizer.normalize(
                    source=self.name,
                    external_id=listing_id,
                    title=record.get("title"),
                    company=tenant.company,
                    url=public_url,
                    location=record.get("locationsText", ""),
                    posted_at=record.get("postedOn"),
                    raw=record,
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Workday listing: %s", error)
                continue
            if job_matches_query(job, query):
                preliminary.append((job, external_path, record))
        preliminary = preliminary[:limit]
        details = await asyncio.gather(
            *(self._fetch_detail(base, path) for _, path, _ in preliminary),
            return_exceptions=True,
        )
        normalized: list[JobPosting] = []
        for (fallback, _, listing), detail in zip(preliminary, details):
            if isinstance(detail, BaseException) or not isinstance(detail, Mapping):
                normalized.append(fallback)
                continue
            info = detail.get("jobPostingInfo", detail)
            if not isinstance(info, Mapping):
                normalized.append(fallback)
                continue
            try:
                normalized.append(
                    self._normalizer.normalize(
                        source=self.name,
                        external_id=(
                            info.get("jobReqId")
                            or info.get("id")
                            or fallback.external_id
                        ),
                        title=info.get("title") or fallback.title,
                        company=tenant.company,
                        url=info.get("externalUrl") or fallback.url,
                        location=(
                            info.get("location")
                            or info.get("locationText")
                            or fallback.location
                        ),
                        description=info.get("jobDescription", ""),
                        employment_type=info.get("timeType"),
                        posted_at=info.get("startDate") or listing.get("postedOn"),
                        raw=info,
                    )
                )
            except (TypeError, ValueError):
                normalized.append(fallback)
        return tuple(normalized)

    async def _fetch_detail(self, base: str, external_path: str) -> object:
        if not external_path:
            return {}
        return (await self._http.get(f"{base}{external_path}")).json()
