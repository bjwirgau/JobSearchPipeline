"""Embedding boundary reserved for semantic matching."""

from __future__ import annotations

from typing import Protocol, Sequence


class EmbeddingService(Protocol):
    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return one embedding vector per input string."""


class EmbeddingNotConfiguredError(RuntimeError):
    pass


class DisabledEmbeddingService:
    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        raise EmbeddingNotConfiguredError("no embedding provider is configured")
