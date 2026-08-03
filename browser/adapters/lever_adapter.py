"""Lever page detection; submission is intentionally not implemented."""

from __future__ import annotations

from .generic_adapter import GenericAdapter


class LeverAdapter(GenericAdapter):
    platform = "lever"

    def supports(self, url: str) -> bool:
        normalized = url.casefold()
        return "lever.co" in normalized or "jobs.lever" in normalized
