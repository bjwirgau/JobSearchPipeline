"""Enrich Greenhouse jobs from Schema.org data embedded in job pages.

The JSON-LD scraping strategy is adapted from Marcus Kyung's MIT-licensed
``greenhouse.io-scraper`` project. See ``THIRD_PARTY_NOTICES.md``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol

from models import JobPosting
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer


LOGGER = logging.getLogger(__name__)


class GreenhouseJobScraper(Protocol):
    async def scrape(
        self,
        jobs: Sequence[JobPosting],
    ) -> Sequence[JobPosting]:
        """Return jobs enriched from their public Greenhouse detail pages."""


class GreenhouseJobPageScraper:
    """Fetch matching job pages and extract their Schema.org JobPosting data."""

    def __init__(
        self,
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
        concurrency: int = 5,
    ) -> None:
        if not 1 <= concurrency <= 20:
            raise ValueError("Greenhouse scraper concurrency must be between 1 and 20")
        self._http = http
        self._normalizer = normalizer
        self._request_limit = asyncio.Semaphore(concurrency)

    async def scrape(
        self,
        jobs: Sequence[JobPosting],
    ) -> tuple[JobPosting, ...]:
        outcomes = await asyncio.gather(
            *(self._scrape_job(job) for job in jobs),
            return_exceptions=True,
        )
        enriched: list[JobPosting] = []
        for job, outcome in zip(jobs, outcomes):
            if isinstance(outcome, BaseException):
                LOGGER.warning(
                    "Greenhouse job page scrape failed for %s: %s",
                    job.url,
                    outcome,
                )
                enriched.append(job)
            else:
                enriched.append(outcome)
        return tuple(enriched)

    async def _scrape_job(self, job: JobPosting) -> JobPosting:
        async with self._request_limit:
            response = await self._http.get(job.url)
        record = _job_record(response.text)
        if record is None:
            raise ValueError("job page does not contain JobPosting JSON-LD")
        return self._normalize(job, record)

    def _normalize(
        self,
        job: JobPosting,
        record: Mapping[str, Any],
    ) -> JobPosting:
        organization = record.get("hiringOrganization")
        company = (
            organization.get("name")
            if isinstance(organization, Mapping)
            else None
        ) or job.company
        scraped_location = _location(record.get("jobLocation"))
        salary = record.get("baseSalary")
        salary = salary if isinstance(salary, Mapping) else {}
        salary_value = salary.get("value")
        salary_value = salary_value if isinstance(salary_value, Mapping) else {}
        employment_type = record.get("employmentType")
        if isinstance(employment_type, list):
            employment_type = ", ".join(str(value) for value in employment_type)
        location_type = str(record.get("jobLocationType") or "")
        is_remote = (
            True
            if "telecommute" in location_type.casefold()
            else job.is_remote
        )
        return self._normalizer.normalize(
            source=job.source,
            external_id=job.external_id,
            title=record.get("title") or record.get("name") or job.title,
            company=company,
            url=record.get("url") or job.url,
            location=scraped_location or job.location,
            description=record.get("description") or job.description,
            skills=(*job.skills, *_skills(record.get("skills"))),
            industries=job.industries,
            responsibilities=job.responsibilities,
            requirements=job.requirements,
            employment_type=employment_type or job.employment_type,
            salary_min=(
                salary_value.get("minValue")
                or salary_value.get("value")
                or job.salary_min
            ),
            salary_max=salary_value.get("maxValue") or job.salary_max,
            salary_currency=salary.get("currency") or job.salary_currency,
            is_remote=is_remote,
            remote_country_codes=job.remote_country_codes,
            posted_at=record.get("datePosted") or job.posted_at,
            raw={
                "greenhouse_api": dict(job.raw),
                "greenhouse_scraper": dict(record),
            },
        )


class _JsonLdScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        self._capturing = (
            tag.casefold() == "script"
            and (attributes.get("type") or "").casefold()
            == "application/ld+json"
        )
        if self._capturing:
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._capturing:
            self.scripts.append("".join(self._parts))
            self._capturing = False


def _job_record(html: str) -> Mapping[str, Any] | None:
    scripts: list[str]
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        parser = _JsonLdScripts()
        parser.feed(html)
        scripts = parser.scripts
    else:
        soup = BeautifulSoup(html, "html.parser")
        scripts = [
            script.string or script.get_text()
            for script in soup.find_all("script", type="application/ld+json")
        ]
    for content in scripts:
        if not content.strip():
            continue
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            continue
        records = _job_records(value)
        if records:
            return records[0]
    return None


def _job_records(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, list):
        return tuple(
            record
            for item in value
            for record in _job_records(item)
        )
    if not isinstance(value, Mapping):
        return ()
    record_type = value.get("@type")
    types = (
        tuple(str(item).casefold() for item in record_type)
        if isinstance(record_type, list)
        else (str(record_type).casefold(),)
    )
    if "jobposting" in types:
        return (value,)
    return _job_records(value.get("@graph", ()))


def _location(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(
            location
            for item in value
            if (location := _location(item))
        )
    if not isinstance(value, Mapping):
        return str(value or "").strip()
    address = value.get("address", value)
    if not isinstance(address, Mapping):
        return str(address or "").strip()
    return ", ".join(
        str(address[field]).strip()
        for field in ("addressLocality", "addressRegion", "addressCountry")
        if address.get(field)
    )


def _skills(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(
            skill.strip()
            for skill in value.replace(";", ",").split(",")
            if skill.strip()
        )
    if isinstance(value, list):
        return tuple(str(skill).strip() for skill in value if str(skill).strip())
    return ()
