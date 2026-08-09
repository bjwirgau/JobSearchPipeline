"""Greenhouse public Job Board API adapter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from models import JobPosting, SearchCriteria, SearchQuery
from services.http_service import HttpClient
from services.job_normalization_service import JobNormalizer

from .base import job_matches_query
from .greenhouse_scraper import GreenhouseJobScraper


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GreenhouseBoard:
    company: str
    token: str

    def __post_init__(self) -> None:
        company = self.company.strip()
        token = self.token.strip().casefold()
        if not company or not token:
            raise ValueError("Greenhouse company and board token must not be empty")
        object.__setattr__(self, "company", company)
        object.__setattr__(self, "token", token)


class GreenhouseJobSource:
    name = "greenhouse"
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(
        self,
        boards: tuple[GreenhouseBoard, ...],
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
        scraper: GreenhouseJobScraper | None = None,
        concurrency: int = 10,
        board_limit: int = 25,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("Greenhouse concurrency must be greater than zero")
        if not 1 <= board_limit <= 1_000:
            raise ValueError("Greenhouse board limit must be between 1 and 1000")
        unique_boards = tuple({board.token: board for board in boards}.values())
        self._boards = unique_boards[:board_limit]
        self._http = http
        self._normalizer = normalizer
        self._scraper = scraper
        self._cache: tuple[JobPosting, ...] | None = None
        self._cache_lock = asyncio.Lock()
        self._scrape_cache: dict[str, JobPosting] = {}
        self._scrape_lock = asyncio.Lock()
        self._request_limit = asyncio.Semaphore(concurrency)

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._boards)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
        jobs = await self._load_jobs()
        matches = tuple(job for job in jobs if job_matches_query(job, query))[:limit]
        if self._scraper is not None and matches:
            matches = await self._scrape_matches(matches)
        return tuple(job for job in matches if job_matches_query(job, query))[:limit]

    async def _scrape_matches(
        self,
        jobs: tuple[JobPosting, ...],
    ) -> tuple[JobPosting, ...]:
        async with self._scrape_lock:
            missing = tuple(
                job for job in jobs if job.external_id not in self._scrape_cache
            )
            if missing:
                scraped = tuple(await self._scraper.scrape(missing))
                self._scrape_cache.update(
                    (job.external_id, job) for job in scraped
                )
            return tuple(
                self._scrape_cache.get(job.external_id, job) for job in jobs
            )

    async def _load_jobs(self) -> tuple[JobPosting, ...]:
        if self._cache is not None:
            return self._cache
        async with self._cache_lock:
            if self._cache is None:
                self._cache = await self._fetch_boards()
        return self._cache

    async def _fetch_boards(self) -> tuple[JobPosting, ...]:
        LOGGER.info("Searching %s Greenhouse job boards", len(self._boards))
        outcomes = await asyncio.gather(
            *(self._fetch_board(board) for board in self._boards),
            return_exceptions=True,
        )
        jobs: list[JobPosting] = []
        failures: list[BaseException] = []
        for board, outcome in zip(self._boards, outcomes):
            if isinstance(outcome, BaseException):
                LOGGER.warning("Greenhouse board %s failed: %s", board.token, outcome)
                failures.append(outcome)
                continue
            jobs.extend(outcome)
        if not jobs and failures:
            raise RuntimeError(f"all Greenhouse boards failed: {failures[0]}")
        return tuple(jobs)

    async def _fetch_board(self, board: GreenhouseBoard) -> tuple[JobPosting, ...]:
        url = f"{self.API_BASE}/{quote(board.token, safe='')}/jobs"
        async with self._request_limit:
            LOGGER.info(
                "Fetching Greenhouse job board for %s (token: %s)",
                board.company,
                board.token,
            )
            response = await self._http.get(url, params={"content": "true"})
        payload = response.json()
        if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
            raise ValueError(f"unexpected Greenhouse response for {board.token}")
        normalized: list[JobPosting] = []
        for record in payload["jobs"]:
            if not isinstance(record, Mapping):
                continue
            location = record.get("location")
            location_name = location.get("name", "") if isinstance(location, Mapping) else ""
            try:
                normalized.append(
                    self._normalizer.normalize(
                        source=self.name,
                        external_id=record.get("id"),
                        title=record.get("title"),
                        company=board.company,
                        url=record.get("absolute_url"),
                        location=location_name,
                        description=record.get("content", ""),
                        posted_at=None,
                        raw=record,
                    )
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Greenhouse job: %s", error)
        return tuple(normalized)
