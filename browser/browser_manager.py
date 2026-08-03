"""Guarded browser lifecycle boundary."""

from __future__ import annotations

from dataclasses import dataclass


class BrowserAutomationDisabledError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BrowserSession:
    session_id: str
    active: bool = False


class BrowserManager:
    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    async def start(self) -> BrowserSession:
        if not self.enabled:
            raise BrowserAutomationDisabledError(
                "browser automation is disabled in Phase 1"
            )
        raise NotImplementedError("a browser runtime has not been configured")

    async def close(self, session: BrowserSession) -> None:
        return None
