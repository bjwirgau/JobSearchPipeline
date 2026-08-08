"""Language-model boundary and Gemini API implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
        """Generate an object conforming to the supplied JSON schema."""


class LLMNotConfiguredError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


class MissingGeminiDependencyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeminiConfig:
    api_key: str = field(repr=False)
    model: str = "gemini-3.5-flash-lite"
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1_500

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("Gemini API key must not be empty")
        if not self.model.strip():
            raise ValueError("Gemini model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("Gemini timeout must be greater than zero")
        if self.max_output_tokens <= 0:
            raise ValueError("Gemini max output tokens must be greater than zero")


class GeminiLLMService:
    """Generate model output through the asynchronous Gemini Developer API."""

    def __init__(self, config: GeminiConfig, *, client: Any | None = None) -> None:
        self._config = config
        if client is None:
            try:
                from google import genai
                from google.genai import types
            except ImportError as error:
                raise MissingGeminiDependencyError(
                    "install Gemini support with: pip install -e ."
                ) from error
            client = genai.Client(
                api_key=config.api_key,
                http_options=types.HttpOptions(
                    timeout=max(1, round(config.timeout_seconds * 1_000)),
                ),
            ).aio
        self._client = client

    async def generate_text(self, prompt: str) -> str:
        try:
            response = await self._client.models.generate_content(
                model=self._config.model,
                contents=prompt,
                config={"max_output_tokens": self._config.max_output_tokens},
            )
        except Exception as error:
            raise LLMResponseError(self._request_error(error)) from error
        return _response_text(response, provider="Gemini")

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            response = await self._client.models.generate_content(
                model=self._config.model,
                contents=prompt,
                config={
                    "max_output_tokens": self._config.max_output_tokens,
                    "response_mime_type": "application/json",
                    "response_json_schema": dict(schema),
                },
            )
        except Exception as error:
            raise LLMResponseError(self._request_error(error)) from error
        raw_text = _response_text(response, provider="Gemini")
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise LLMResponseError("Gemini returned invalid structured JSON") from error
        if not isinstance(value, Mapping):
            raise LLMResponseError("Gemini structured output must be an object")
        return value

    def _request_error(self, error: Exception) -> str:
        detail = str(error).strip().replace(self._config.api_key, "[REDACTED]")
        suffix = f": {detail}" if detail else ""
        return f"Gemini request failed: {type(error).__name__}{suffix}"


class DisabledLLMService:
    async def generate_text(self, prompt: str) -> str:
        raise LLMNotConfiguredError(
            "LLM matching requires GEMINI_API_KEY to be configured"
        )

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise LLMNotConfiguredError(
            "LLM matching requires GEMINI_API_KEY to be configured"
        )


def _response_text(response: Any, *, provider: str) -> str:
    value = getattr(response, "text", None)
    if not isinstance(value, str) or not value.strip():
        raise LLMResponseError(f"{provider} returned no text output")
    return value.strip()
