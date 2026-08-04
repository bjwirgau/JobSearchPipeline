"""Source-adapter contract and a local in-memory implementation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from models import JobPosting, SearchCriteria, SearchQuery


class JobSourceService(Protocol):
    name: str

    def supports(self, criteria: SearchCriteria) -> bool:
        """Return whether this source accepts the requested search shape."""

    async def search(
        self,
        query: SearchQuery,
        *,
        limit: int,
    ) -> Sequence[JobPosting]:
        """Fetch and normalize source results into shared job models."""


class InMemoryJobSource:
    """Deterministic source used by tests and local workflow demonstrations."""

    def __init__(self, name: str, jobs: Sequence[JobPosting] = ()) -> None:
        self.name = name
        self._jobs = tuple(jobs)

    def supports(self, criteria: SearchCriteria) -> bool:
        return True

    async def search(
        self,
        query: SearchQuery,
        *,
        limit: int,
    ) -> Sequence[JobPosting]:
        title = (query.title or "").casefold()
        location = (query.location or "").casefold()
        matching = (
            job
            for job in self._jobs
            if (not title or title in job.title.casefold())
            and (
                not location
                or location in job.location.casefold()
                or job.is_remote is True
            )
        )
        return tuple(matching)[:limit]
