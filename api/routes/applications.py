"""Application read handlers."""

from __future__ import annotations

from models import ApplicationStatus
from repositories import ApplicationRepository


def list_applications(
    repository: ApplicationRepository,
    *,
    status: ApplicationStatus = ApplicationStatus.REVIEW_REQUIRED,
) -> list[dict[str, object]]:
    return [application.to_dict() for application in repository.list_by_status(status)]
