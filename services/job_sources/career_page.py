"""Company career-page adapter for Schema.org JobPosting JSON-LD."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Mapping, Protocol

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer
from utils.hashing import stable_hash

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)


class PageLoader(Protocol):
    async def load(self, url: str) -> str:
        """Render and return page HTML."""


@dataclass(frozen=True, slots=True)
class CareerPage:
    company: str
    url: str


class _JsonLdScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self._parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self._capturing = (
            tag.casefold() == "script"
            and (attributes.get("type") or "").casefold() == "application/ld+json"
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


class CareerPageJobSource:
    name = "career_page"

    def __init__(
        self,
        pages: tuple[CareerPage, ...],
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
        browser_loader: PageLoader | None = None,
    ) -> None:
        self._pages = pages
        self._http = http
        self._normalizer = normalizer
        self._browser_loader = browser_loader

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._pages)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        outcomes = await asyncio.gather(
            *(self._fetch_page(page) for page in self._pages),
            return_exceptions=True,
        )
        jobs: list[JobPosting] = []
        failures: list[BaseException] = []
        for page, outcome in zip(self._pages, outcomes):
            if isinstance(outcome, BaseException):
                LOGGER.warning("Career page %s failed: %s", page.url, outcome)
                failures.append(outcome)
                continue
            jobs.extend(outcome)
        if not jobs and failures:
            raise RuntimeError(f"all career pages failed: {failures[0]}")
        return tuple(job for job in jobs if job_matches_query(job, query))[:limit]

    async def _fetch_page(self, page: CareerPage) -> tuple[JobPosting, ...]:
        html = (await self._http.get(page.url)).text
        records = self._records(html)
        if not records and self._browser_loader:
            records = self._records(await self._browser_loader.load(page.url))
        normalized: list[JobPosting] = []
        for record in records:
            try:
                normalized.append(self._normalize_record(page, record))
            except (TypeError, ValueError, KeyError) as error:
                LOGGER.warning("Skipping invalid JSON-LD job on %s: %s", page.url, error)
        return tuple(normalized)

    def _normalize_record(
        self,
        page: CareerPage,
        record: Mapping[str, Any],
    ) -> JobPosting:
        organization = record.get("hiringOrganization")
        company = (
            organization.get("name")
            if isinstance(organization, Mapping)
            else page.company
        ) or page.company
        location = self._location(record.get("jobLocation"))
        salary = record.get("baseSalary")
        salary = salary if isinstance(salary, Mapping) else {}
        salary_value = salary.get("value")
        salary_value = salary_value if isinstance(salary_value, Mapping) else {}
        raw_skills = record.get("skills", ())
        if isinstance(raw_skills, str):
            skills = tuple(part.strip() for part in raw_skills.split(",") if part.strip())
        elif isinstance(raw_skills, list):
            skills = tuple(str(part) for part in raw_skills)
        else:
            skills = ()
        url = record.get("url") or page.url
        identifier = record.get("identifier")
        if isinstance(identifier, Mapping):
            identifier = identifier.get("value") or identifier.get("name")
        location_type = str(record.get("jobLocationType", ""))
        employment = record.get("employmentType")
        if isinstance(employment, list):
            employment = ", ".join(str(value) for value in employment)
        return self._normalizer.normalize(
            source=self.name,
            external_id=identifier or stable_hash(str(url)),
            title=record.get("title") or record.get("name"),
            company=company,
            url=url,
            location=location,
            description=record.get("description", ""),
            skills=skills,
            employment_type=employment,
            salary_min=salary_value.get("minValue") or salary_value.get("value"),
            salary_max=salary_value.get("maxValue"),
            salary_currency=salary.get("currency"),
            is_remote="telecommute" in location_type.casefold() or None,
            posted_at=record.get("datePosted"),
            raw=record,
        )

    @classmethod
    def _records(cls, html: str) -> tuple[Mapping[str, Any], ...]:
        scripts: list[str]
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            parser = _JsonLdScripts()
            parser.feed(html)
            scripts = parser.scripts
        else:
            soup = BeautifulSoup(html, "html.parser")
            scripts = [script.get_text() for script in soup.find_all("script", type="application/ld+json")]
        records: list[Mapping[str, Any]] = []
        for script in scripts:
            try:
                value = json.loads(script)
            except json.JSONDecodeError:
                continue
            records.extend(cls._job_records(value))
        return tuple(records)

    @classmethod
    def _job_records(cls, value: object) -> list[Mapping[str, Any]]:
        if isinstance(value, list):
            records: list[Mapping[str, Any]] = []
            for item in value:
                records.extend(cls._job_records(item))
            return records
        if not isinstance(value, Mapping):
            return []
        record_type = value.get("@type")
        if record_type == "JobPosting" or (
            isinstance(record_type, list) and "JobPosting" in record_type
        ):
            return [value]
        return cls._job_records(value.get("@graph", []))

    @staticmethod
    def _location(value: object) -> str:
        if isinstance(value, list):
            return "; ".join(
                location for item in value if (location := CareerPageJobSource._location(item))
            )
        if not isinstance(value, Mapping):
            return str(value or "")
        address = value.get("address", value)
        if not isinstance(address, Mapping):
            return str(address or "")
        return ", ".join(
            str(address[field]).strip()
            for field in ("addressLocality", "addressRegion", "addressCountry")
            if address.get(field)
        )
