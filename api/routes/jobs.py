"""Job read handlers."""

from __future__ import annotations

from repositories import JobRepository


def list_jobs(repository: JobRepository, *, limit: int = 100) -> list[dict[str, object]]:
    return [job.to_dict() for job in repository.list_recent(limit=limit)]
