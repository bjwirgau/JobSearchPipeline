"""Greenhouse page detection; submission is intentionally not implemented."""

from __future__ import annotations

from .generic_adapter import GenericAdapter


class GreenhouseAdapter(GenericAdapter):
    platform = "greenhouse"

    def supports(self, url: str) -> bool:
        normalized = url.casefold()
        return "greenhouse.io" in normalized or "boards.greenhouse" in normalized
