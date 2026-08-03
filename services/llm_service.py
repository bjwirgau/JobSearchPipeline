"""Language-model boundary; no provider is configured in Phase 1."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class LLMService(Protocol):
    async def generate_text(self, prompt: str) -> str:
        """Generate text from a fully rendered prompt."""

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Generate an object conforming to the supplied schema."""


class LLMNotConfiguredError(RuntimeError):
    pass


class DisabledLLMService:
    async def generate_text(self, prompt: str) -> str:
        raise LLMNotConfiguredError("no language-model provider is configured")

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise LLMNotConfiguredError("no language-model provider is configured")
