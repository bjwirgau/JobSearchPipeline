"""Guarded application submission boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from models import Application, ApplicationStatus, ApplicationValidation
from repositories import ApplicationRepository
from utils.dates import utc_now


class ApplicationGateway(Protocol):
    async def submit(self, application: Application) -> str:
        """Submit an approved application and return an external reference."""


class ApplicationSubmissionDisabledError(RuntimeError):
    pass


class ApplyAgent:
    def __init__(
        self,
        *,
        repository: ApplicationRepository,
        gateway: ApplicationGateway | None = None,
        enabled: bool = False,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._enabled = enabled

    async def submit(
        self,
        application: Application,
        validation: ApplicationValidation,
    ) -> Application:
        if not self._enabled:
            raise ApplicationSubmissionDisabledError(
                "application submission is disabled in configuration"
            )
        if not validation.valid:
            raise ValueError("application failed validation")
        if not self._gateway:
            raise ApplicationSubmissionDisabledError("no application gateway is configured")
        reference = await self._gateway.submit(application)
        submitted = replace(
            application,
            status=ApplicationStatus.SUBMITTED,
            notes=f"{application.notes}\nSubmission reference: {reference}".strip(),
            submitted_at=utc_now(),
            updated_at=utc_now(),
        )
        self._repository.save(submitted)
        return submitted
