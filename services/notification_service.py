"""Notification boundary for review requests and workflow events."""

from __future__ import annotations

import logging
from typing import Mapping, Protocol


class NotificationService(Protocol):
    async def notify(
        self,
        event: str,
        message: str,
        *,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        """Deliver a workflow notification."""


class LoggingNotificationService:
    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    async def notify(
        self,
        event: str,
        message: str,
        *,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self._logger.info("event=%s message=%s metadata=%s", event, message, metadata or {})
