"""Search-stage orchestration with pluggable, normalized job sources."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from models import (
    JobPosting,
    MatchResult,
    SearchCriteria,
    SearchFailure,
    SearchQuery,
    SearchRunResult,
)
from repositories import JobProspectRepository
from services import JobSourceService
from utils.countries import remote_country_is_eligible
from utils.text import normalize_text


class SearchDisabledError(RuntimeError):
    pass


class UnknownJobSourceError(ValueError):
    pass


class NoJobSourcesError(ValueError):
    pass


class SearchQueryBuilder:
    def build(self, criteria: SearchCriteria) -> tuple[SearchQuery, ...]:
        titles: tuple[str | None, ...] = criteria.job_titles or (None,)
        locations: tuple[str | None, ...] = (
            (None,)
            if criteria.remote_only
            else criteria.locations or (None,)
        )
        queries: list[SearchQuery] = []
        seen: set[tuple[str, str, bool]] = set()
        for title in titles:
            for location in locations:
                terms = [title] if title else list(
                    criteria.required_keywords[:3] or criteria.skills[:3]
                )
                if criteria.remote_only:
                    terms.append("remote")
                query = SearchQuery(
                    text=" ".join(terms),
                    title=title,
                    skills=criteria.skills,
                    required_keywords=criteria.required_keywords,
                    location=location,
                    location_radius_miles=(
                        None
                        if criteria.remote_only
                        else criteria.location_radius_miles
                    ),
                    remote_only=criteria.remote_only,
                    remote_country=criteria.remote_country,
                    employment_types=criteria.employment_types,
                    minimum_salary=criteria.minimum_salary,
                    excluded_keywords=criteria.excluded_keywords,
                    max_age_days=criteria.max_age_days,
                )
                signature = (
                    normalize_text(query.text),
                    normalize_text(query.location or ""),
                    query.remote_only,
                )
                if signature not in seen:
                    queries.append(query)
                    seen.add(signature)
        return tuple(queries)


class FingerprintDeduplicator:
    def deduplicate(self, jobs: Sequence[JobPosting]) -> tuple[JobPosting, ...]:
        unique: dict[str, JobPosting] = {}
        for job in jobs:
            unique.setdefault(job.deduplication_key, job)
        return tuple(unique.values())


class SearchAgent:
    """Construct, execute, filter, combine, deduplicate, and store searches."""

    def __init__(
        self,
        *,
        sources: Sequence[JobSourceService],
        repository: JobProspectRepository,
        enabled: bool = False,
        query_builder: SearchQueryBuilder | None = None,
        deduplicator: FingerprintDeduplicator | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._sources: dict[str, JobSourceService] = {}
        for source in sources:
            key = normalize_text(source.name)
            if not key or key in self._sources:
                raise ValueError(f"invalid or duplicate source name: {source.name!r}")
            self._sources[key] = source
        self._repository = repository
        self._enabled = enabled
        self._query_builder = query_builder or SearchQueryBuilder()
        self._deduplicator = deduplicator or FingerprintDeduplicator()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def search(self, criteria: SearchCriteria) -> SearchRunResult:
        if not self._enabled:
            raise SearchDisabledError(
                "job search is disabled; set JOB_AGENT_SEARCH_ENABLED=true after "
                "configuring a source"
            )
        queries = self._query_builder.build(criteria)
        sources = self.select_sources(criteria)
        requests = [(source, query) for source in sources for query in queries]
        outcomes = await asyncio.gather(
            *(
                self._request(source, query, criteria.results_per_query)
                for source, query in requests
            ),
            return_exceptions=True,
        )

        fetched: list[JobPosting] = []
        failures: list[SearchFailure] = []
        for (source, query), outcome in zip(requests, outcomes):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if isinstance(outcome, BaseException):
                failures.append(
                    SearchFailure(
                        source=source.name,
                        query=query,
                        error_type=type(outcome).__name__,
                        message=str(outcome),
                    )
                )
            else:
                fetched.extend(outcome)

        eligible = tuple(job for job in fetched if self._passes_filters(job, criteria))
        deduplicated = self._deduplicator.deduplicate(eligible)
        stored_count = self._repository.save_jobs(deduplicated)
        return SearchRunResult(
            queries=queries,
            selected_sources=tuple(source.name for source in sources),
            fetched_count=len(fetched),
            eligible_count=len(eligible),
            deduplicated_count=len(deduplicated),
            stored_count=stored_count,
            jobs=deduplicated,
            failures=tuple(failures),
        )

    def store_matches(self, matches: Sequence[MatchResult]) -> int:
        return self._repository.update_matches(matches)

    def unmatched_jobs(
        self,
        jobs: Sequence[JobPosting],
    ) -> tuple[JobPosting, ...]:
        matched_ids = self._repository.matched_job_ids(
            tuple(job.job_id for job in jobs)
        )
        return tuple(job for job in jobs if job.job_id not in matched_ids)

    def select_sources(self, criteria: SearchCriteria) -> tuple[JobSourceService, ...]:
        if criteria.source_names:
            requested = tuple(normalize_text(name) for name in criteria.source_names)
            unknown = [name for name in requested if name not in self._sources]
            if unknown:
                raise UnknownJobSourceError(f"unknown job source(s): {', '.join(unknown)}")
            candidates = tuple(self._sources[name] for name in dict.fromkeys(requested))
        else:
            candidates = tuple(self._sources.values())
        selected = tuple(source for source in candidates if source.supports(criteria))
        if not selected:
            raise NoJobSourcesError("no configured source supports this search")
        return selected

    async def _request(
        self,
        source: JobSourceService,
        query: SearchQuery,
        limit: int,
    ) -> tuple[JobPosting, ...]:
        jobs = tuple(await source.search(query, limit=limit))
        if not all(isinstance(job, JobPosting) for job in jobs):
            raise TypeError(f"source {source.name} returned a non-JobPosting value")
        return jobs

    def _passes_filters(self, job: JobPosting, criteria: SearchCriteria) -> bool:
        if criteria.remote_only and job.is_remote is not True:
            return False
        if (
            criteria.remote_country
            and job.is_remote is True
            and not remote_country_is_eligible(
                criteria.remote_country,
                job.remote_country_codes,
                job.location,
            )
        ):
            return False
        if criteria.locations and job.is_remote is not True:
            location = normalize_text(job.location)
            if not any(normalize_text(value) in location for value in criteria.locations):
                return False
        if criteria.employment_types and _employment_key(job.employment_type or "") not in {
            _employment_key(value) for value in criteria.employment_types
        }:
            return False
        highest_salary = job.salary_max if job.salary_max is not None else job.salary_min
        if (
            criteria.minimum_salary is not None
            and highest_salary is not None
            and highest_salary < criteria.minimum_salary
        ):
            return False
        haystack = normalize_text(
            " ".join(
                (
                    job.title,
                    job.company,
                    job.description,
                    *job.skills,
                    *job.requirements,
                )
            )
        )
        if any(
            normalize_text(value) not in haystack
            for value in criteria.required_keywords
        ):
            return False
        if any(normalize_text(value) in haystack for value in criteria.excluded_keywords):
            return False
        if criteria.max_age_days is not None and job.posted_at is not None:
            posted_at = job.posted_at
            if posted_at.tzinfo is None:
                posted_at = posted_at.replace(tzinfo=timezone.utc)
            now = self._clock()
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            if posted_at < now - timedelta(days=criteria.max_age_days):
                return False
        return True


def _employment_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())
