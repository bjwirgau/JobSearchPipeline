"""LinkedIn job discovery through an Apify Store Actor."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping
from urllib.parse import urlencode

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer, parse_salary
from utils.countries import COUNTRY_NAMES

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)

DEFAULT_ACTOR_ID = "automation-lab/linkedin-jobs-scraper"
MAX_JOBS_PER_RUN = 1000


class LinkedInWorkplaceType(str, Enum):
    """Workplace filter codes accepted by the configured LinkedIn Actor."""

    ON_SITE = "1"
    REMOTE = "2"
    HYBRID = "3"


@dataclass(frozen=True, slots=True)
class ApifyLinkedInConfig:
    api_token: str
    actor_id: str = DEFAULT_ACTOR_ID
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if not self.api_token.strip():
            raise ValueError("Apify API token must not be empty")
        if not self.actor_id.strip():
            raise ValueError("Apify Actor ID must not be empty")
        if self.timeout_seconds <= 0 or self.timeout_seconds > 300:
            raise ValueError("Apify timeout must be between 1 and 300 seconds")


class LinkedInJobSource:
    name = "linkedin"

    def __init__(
        self,
        config: ApifyLinkedInConfig,
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._config = config
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._config.api_token)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        actor_limit = min(limit, MAX_JOBS_PER_RUN)
        response = await self._http.post_json(
            self._run_url(actor_limit),
            self._actor_input(query, actor_limit),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._config.api_token}",
            },
        )
        records = response.json()
        if not isinstance(records, list):
            raise ValueError("unexpected Apify LinkedIn dataset response")

        jobs: list[JobPosting] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            salary_min, salary_max, salary_currency = parse_salary(
                str(record.get("salary", ""))
            )
            is_remote = _remote_status(
                record.get("workplaceType"),
                remote_only=query.remote_only,
            )
            industries = _strings(record.get("industries"))
            skills = _strings(record.get("skills"))
            try:
                job = self._normalizer.normalize(
                    source=self.name,
                    external_id=(
                        record.get("id")
                        or record.get("jobId")
                        or record.get("jobPostingId")
                    ),
                    title=record.get("title") or record.get("jobTitle"),
                    company=record.get("companyName") or record.get("company"),
                    url=(
                        record.get("url")
                        or record.get("jobUrl")
                        or record.get("jobPostingUrl")
                        or record.get("applyUrl")
                    ),
                    location=record.get("location", ""),
                    description=(
                        record.get("descriptionText")
                        or record.get("description")
                        or record.get("descriptionHtml")
                        or ""
                    ),
                    skills=skills,
                    industries=industries,
                    employment_type=(
                        record.get("employmentType") or record.get("jobType")
                    ),
                    salary_min=record.get("salaryMin") or salary_min,
                    salary_max=record.get("salaryMax") or salary_max,
                    salary_currency=(
                        record.get("salaryCurrency") or salary_currency
                    ),
                    is_remote=is_remote,
                    remote_country_codes=(
                        (query.remote_country,)
                        if is_remote and query.remote_country
                        else ()
                    ),
                    posted_at=(
                        record.get("postedAt")
                        or record.get("listedAt")
                        or record.get("datePosted")
                    ),
                    raw=record,
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Apify LinkedIn job: %s", error)
                continue
            if job_matches_query(job, query):
                jobs.append(job)
        return tuple(jobs)[:actor_limit]

    def _run_url(self, limit: int) -> str:
        actor_id = self._config.actor_id.strip().replace("/", "~")
        parameters = urlencode(
            {
                "clean": "true",
                "maxItems": limit,
                "timeout": f"{self._config.timeout_seconds:g}",
            }
        )
        return (
            f"https://api.apify.com/v2/acts/{actor_id}/"
            f"run-sync-get-dataset-items?{parameters}"
        )

    @staticmethod
    def _actor_input(query: SearchQuery, limit: int) -> dict[str, object]:
        required_terms = " ".join(query.required_keywords)
        search_query = " ".join(
            value for value in (query.title or query.text, required_terms) if value
        )
        payload: dict[str, object] = {
            "searchQuery": search_query,
            "maxJobs": limit,
            "scrapeJobDetails": True,
            "sortBy": "DD",
        }
        location = (
            _country_name(query.remote_country)
            if query.remote_only
            else query.location
        )
        if location:
            payload["location"] = location
        if query.remote_only:
            payload["workplaceType"] = LinkedInWorkplaceType.REMOTE.value
        if len(query.employment_types) == 1:
            job_type = _job_type(query.employment_types[0])
            if job_type:
                payload["jobType"] = job_type
        date_posted = _date_posted(query.max_age_days)
        if date_posted:
            payload["datePosted"] = date_posted
        return payload


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _remote_status(value: object, *, remote_only: bool) -> bool | None:
    if remote_only:
        return True
    workplace_type = str(value or "").strip().casefold()
    if workplace_type in {
        LinkedInWorkplaceType.REMOTE.value,
        "remote",
    }:
        return True
    if workplace_type in {
        LinkedInWorkplaceType.ON_SITE.value,
        LinkedInWorkplaceType.HYBRID.value,
        "on-site",
        "onsite",
        "hybrid",
    }:
        return False
    return None


def _country_name(code: str | None) -> str | None:
    if not code:
        return None
    preferred = {"gb": "United Kingdom", "us": "United States"}
    if code in preferred:
        return preferred[code]
    aliases = COUNTRY_NAMES.get(code)
    return aliases[0].title() if aliases else code.upper()


def _job_type(value: str) -> str | None:
    normalized = value.casefold().replace("_", "-").replace(" ", "-")
    return {
        "full-time": "F",
        "part-time": "P",
        "contract": "C",
        "temporary": "T",
        "internship": "I",
        "intern": "I",
    }.get(normalized)


def _date_posted(max_age_days: int | None) -> str | None:
    if max_age_days is None or max_age_days > 30:
        return None
    if max_age_days <= 1:
        return "r86400"
    if max_age_days <= 7:
        return "r604800"
    return "r2592000"
