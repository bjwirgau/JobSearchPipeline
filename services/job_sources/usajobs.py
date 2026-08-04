"""Criteria-based federal job discovery through the official USAJOBS API."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Mapping, Sequence

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer

from .base import job_matches_query


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class USAJobsCredentials:
    email: str
    api_key: str


class USAJobsJobSource:
    name = "usajobs"
    API_URL = "https://data.usajobs.gov/api/search"

    def __init__(
        self,
        credentials: USAJobsCredentials,
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._credentials = credentials
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        configured = bool(self._credentials.email and self._credentials.api_key)
        country_supported = not (
            criteria.remote_only
            and criteria.remote_country
            and criteria.remote_country != "us"
        )
        return configured and country_supported

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        response = await self._http.get(
            self.API_URL,
            params=self._parameters(query, limit),
            headers={
                "Host": "data.usajobs.gov",
                "User-Agent": self._credentials.email,
                "Authorization-Key": self._credentials.api_key,
            },
        )
        payload = response.json()
        search_result = payload.get("SearchResult") if isinstance(payload, Mapping) else None
        records = (
            search_result.get("SearchResultItems")
            if isinstance(search_result, Mapping)
            else None
        )
        if not isinstance(records, list):
            raise ValueError("unexpected USAJOBS search response")

        jobs: list[JobPosting] = []
        for record in records:
            descriptor = (
                record.get("MatchedObjectDescriptor")
                if isinstance(record, Mapping)
                else None
            )
            if not isinstance(descriptor, Mapping):
                continue
            try:
                job = self._normalize(record, descriptor, query)
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid USAJOBS job: %s", error)
                continue
            if job_matches_query(job, query):
                jobs.append(job)
        return tuple(jobs)[:limit]

    @staticmethod
    def _parameters(query: SearchQuery, limit: int) -> dict[str, object]:
        params: dict[str, object] = {"ResultsPerPage": min(limit, 500), "Fields": "Full"}
        if query.title:
            params["PositionTitle"] = query.title
        keywords = query.required_keywords or (() if query.title else query.skills[:3])
        if keywords:
            params["Keyword"] = " ".join(keywords)
        if query.location:
            params["LocationName"] = query.location
        if query.location and query.location_radius_miles is not None:
            params["Radius"] = query.location_radius_miles
        if query.minimum_salary is not None:
            params["RemunerationMinimumAmount"] = query.minimum_salary
        if query.max_age_days is not None:
            params["DatePosted"] = min(query.max_age_days, 60)
        if query.remote_only:
            params["RemoteIndicator"] = "True"
        if len(query.employment_types) == 1:
            schedule_codes = {
                "fulltime": "1",
                "parttime": "2",
                "shiftwork": "3",
                "intermittent": "4",
                "jobsharing": "5",
            }
            key = "".join(
                character
                for character in query.employment_types[0].casefold()
                if character.isalnum()
            )
            if key in schedule_codes:
                params["PositionScheduleTypeCode"] = schedule_codes[key]
        return params

    def _normalize(
        self,
        record: Mapping[str, object],
        descriptor: Mapping[str, object],
        query: SearchQuery,
    ) -> JobPosting:
        user_area = descriptor.get("UserArea")
        user_area = user_area if isinstance(user_area, Mapping) else {}
        details = user_area.get("Details")
        details = details if isinstance(details, Mapping) else {}

        requirements = self._strings(details.get("KeyRequirements"))
        requirements += self._strings(
            (descriptor.get("QualificationSummary"), details.get("Requirements"))
        )
        responsibilities = self._strings((details.get("MajorDuties"),))
        description_parts = self._strings(
            (
                details.get("JobSummary"),
                descriptor.get("QualificationSummary"),
                details.get("MajorDuties"),
                details.get("Requirements"),
                details.get("Evaluations"),
            )
        )

        categories = descriptor.get("JobCategory")
        industries = tuple(
            str(value.get("Name", "")).strip()
            for value in categories
            if isinstance(value, Mapping) and value.get("Name")
        ) if isinstance(categories, list) else ()
        schedules = descriptor.get("PositionSchedule")
        employment_type = self._first_mapping_value(schedules, "Name")
        remuneration = descriptor.get("PositionRemuneration")
        salary = remuneration[0] if isinstance(remuneration, list) and remuneration else {}
        salary = salary if isinstance(salary, Mapping) else {}
        is_annual = salary.get("RateIntervalCode") == "PA" or str(
            salary.get("Description", "")
        ).casefold() == "per year"

        return self._normalizer.normalize(
            source=self.name,
            external_id=descriptor.get("PositionID") or record.get("MatchedObjectId"),
            title=descriptor.get("PositionTitle"),
            company=descriptor.get("OrganizationName") or descriptor.get("DepartmentName"),
            url=descriptor.get("PositionURI"),
            location=descriptor.get("PositionLocationDisplay", ""),
            description=" ".join(description_parts),
            industries=industries,
            responsibilities=responsibilities,
            requirements=requirements,
            employment_type=employment_type,
            salary_min=salary.get("MinimumRange") if is_annual else None,
            salary_max=salary.get("MaximumRange") if is_annual else None,
            salary_currency="USD" if is_annual else None,
            is_remote=True if query.remote_only else None,
            remote_country_codes=("us",),
            posted_at=descriptor.get("PublicationStartDate"),
            raw=descriptor,
        )

    @staticmethod
    def _strings(value: object) -> tuple[str, ...]:
        values: Sequence[object]
        if isinstance(value, (list, tuple)):
            values = value
        else:
            values = (value,)
        return tuple(str(item).strip() for item in values if item and str(item).strip())

    @staticmethod
    def _first_mapping_value(value: object, key: str) -> object:
        if not isinstance(value, list) or not value or not isinstance(value[0], Mapping):
            return None
        return value[0].get(key)
