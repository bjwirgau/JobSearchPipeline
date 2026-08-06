"""Job-prospect read handlers."""

from __future__ import annotations

from repositories import JobProspectRepository


def list_job_prospects(
    repository: JobProspectRepository,
    *,
    limit: int = 100,
) -> list[dict[str, object]]:
    return [prospect.to_dict() for prospect in repository.list_ranked(limit=limit)]
