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


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GreenhouseBoard:
    company: str
    token: str


class GreenhouseJobSource:
    name = "greenhouse"
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(
        self,
        boards: tuple[GreenhouseBoard, ...],
        *,
        http: HttpClient,
        normalizer: JobNormalizer,
    ) -> None:
        self._boards = boards
        self._http = http
        self._normalizer = normalizer

    def supports(self, criteria: SearchCriteria) -> bool:
        return bool(self._boards)

    async def search(self, query: SearchQuery, *, limit: int) -> tuple[JobPosting, ...]:
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
        return tuple(job for job in jobs if job_matches_query(job, query))[:limit]

    async def _fetch_board(self, board: GreenhouseBoard) -> tuple[JobPosting, ...]:
        url = f"{self.API_BASE}/{quote(board.token, safe='')}/jobs"
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
                        posted_at=record.get("updated_at"),
                        raw=record,
                    )
                )
            except (TypeError, ValueError) as error:
                LOGGER.warning("Skipping invalid Greenhouse job: %s", error)
        return tuple(normalized)
