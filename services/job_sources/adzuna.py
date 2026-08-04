"""Criteria-based discovery through Adzuna's job search API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)

COUNTRY_CURRENCIES = {
    "au": "AUD",
    "ca": "CAD",
    "ch": "CHF",
    "de": "EUR",
    "es": "EUR",
    "fr": "EUR",
    "gb": "GBP",
    "in": "INR",
    "it": "EUR",
    "mx": "MXN",
    "nl": "EUR",
    "nz": "NZD",
    "pl": "PLN",
    "sg": "SGD",
    "us": "USD",
    "za": "ZAR",
}


@dataclass(frozen=True, slots=True)
class AdzunaCredentials:
    app_id: str
    app_key: str
    country: str = "us"


class AdzunaJobSource:
    """Search Adzuna's cross-company index using shared search criteria."""

    name = "adzuna"
    API_BASE = "https://api.adzuna.com/v1/api/jobs"

    def __init__(
        self,
        credentials: AdzunaCredentials,
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._credentials = credentials
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        configured = bool(self._credentials.app_id and self._credentials.app_key)
        country_supported = not (
            criteria.remote_only
            and criteria.remote_country
            and criteria.remote_country != self._credentials.country
        )
        return configured and country_supported

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        url = f"{self.API_BASE}/{self._credentials.country}/search/1"
        response = await self._http.get(url, params=self._parameters(query, limit))
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise ValueError("unexpected Adzuna search response")

        jobs: list[JobPosting] = []
        for record in payload["results"]:
            if not isinstance(record, Mapping):
                continue
            company = record.get("company")
            company = company if isinstance(company, Mapping) else {}
            location = record.get("location")
            location = location if isinstance(location, Mapping) else {}
            category = record.get("category")
            category = category if isinstance(category, Mapping) else {}
            industries = (str(category.get("label", "")),) if category.get("label") else ()
            try:
                job = self._normalizer.normalize(
                    source=self.name,
                    external_id=record.get("id"),
                    title=record.get("title"),
                    company=company.get("display_name") or "Unknown employer",
                    url=record.get("redirect_url"),
                    location=location.get("display_name", ""),
                    description=record.get("description", ""),
                    industries=industries,
                    employment_type=record.get("contract_time") or record.get("contract_type"),
                    salary_min=record.get("salary_min"),
                    salary_max=record.get("salary_max"),
                    salary_currency=COUNTRY_CURRENCIES.get(self._credentials.country),
                    remote_country_codes=(self._credentials.country,),
                    posted_at=record.get("created"),
                    raw=record,
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Adzuna job: %s", error)
                continue
            if job_matches_query(job, query):
                jobs.append(job)
        return tuple(jobs)[:limit]

    def _parameters(self, query: SearchQuery, limit: int) -> dict[str, object]:
        search_terms = query.title or query.text
        if query.remote_only and "remote" not in search_terms.casefold():
            search_terms = f"{search_terms} remote".strip()
        params: dict[str, object] = {
            "app_id": self._credentials.app_id,
            "app_key": self._credentials.app_key,
            "results_per_page": limit,
            "what": search_terms,
            "sort_by": "date",
            "content-type": "application/json",
        }
        if query.required_keywords:
            params["what_and"] = " ".join(query.required_keywords)
        if query.excluded_keywords:
            params["what_exclude"] = " ".join(query.excluded_keywords)
        if query.location:
            params["where"] = query.location
        if query.location_radius_miles is not None:
            params["distance"] = round(query.location_radius_miles * 1.60934)
        if query.minimum_salary is not None:
            params["salary_min"] = query.minimum_salary
        if query.max_age_days is not None:
            params["max_days_old"] = query.max_age_days
        if len(query.employment_types) == 1:
            employment_key = (
                query.employment_types[0]
                .casefold()
                .replace("-", "_")
                .replace(" ", "_")
            )
            if employment_key in {"full_time", "part_time", "contract", "permanent"}:
                params[employment_key] = "1"
        return params
