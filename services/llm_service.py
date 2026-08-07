"""Language-model boundary and OpenAI Responses API implementation."""

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


class MissingOpenAIDependencyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpenAIConfig:
    api_key: str = field(repr=False)
    model: str = "gpt-5.6-terra"
    reasoning_effort: str = "low"
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1_500

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not self.model.strip():
            raise ValueError("OpenAI model must not be empty")
        if self.reasoning_effort not in {
            "none",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ValueError("invalid OpenAI reasoning effort")
        if self.timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be greater than zero")
        if self.max_output_tokens <= 0:
            raise ValueError("OpenAI max output tokens must be greater than zero")


class OpenAILLMService:
    """Generate model output through OpenAI's asynchronous Responses API."""

    def __init__(self, config: OpenAIConfig, *, client: Any | None = None) -> None:
        self._config = config
        if client is None:
            try:
                from openai import AsyncOpenAI
            except ImportError as error:
                raise MissingOpenAIDependencyError(
                    "install OpenAI support with: pip install -e ."
                ) from error
            client = AsyncOpenAI(
                api_key=config.api_key,
                timeout=config.timeout_seconds,
                max_retries=2,
            )
        self._client = client

    async def generate_text(self, prompt: str) -> str:
        try:
            response = await self._client.responses.create(
                model=self._config.model,
                input=prompt,
                reasoning={"effort": self._config.reasoning_effort},
                text={"verbosity": "low"},
                max_output_tokens=self._config.max_output_tokens,
                store=False,
            )
        except Exception as error:
            raise LLMResponseError(
                f"OpenAI request failed: {type(error).__name__}"
            ) from error
        return _response_text(response)

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        try:
            response = await self._client.responses.create(
                model=self._config.model,
                input=prompt,
                reasoning={"effort": self._config.reasoning_effort},
                text={
                    "verbosity": "low",
                    "format": {
                        "type": "json_schema",
                        "name": "structured_response",
                        "schema": dict(schema),
                        "strict": True,
                    },
                },
                max_output_tokens=self._config.max_output_tokens,
                store=False,
            )
        except Exception as error:
            raise LLMResponseError(
                f"OpenAI request failed: {type(error).__name__}"
            ) from error
        raw_text = _response_text(response)
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise LLMResponseError("OpenAI returned invalid structured JSON") from error
        if not isinstance(value, Mapping):
            raise LLMResponseError("OpenAI structured output must be an object")
        return value


class DisabledLLMService:
    async def generate_text(self, prompt: str) -> str:
        raise LLMNotConfiguredError(
            "LLM matching requires OPENAI_API_KEY to be configured"
        )

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise LLMNotConfiguredError(
            "LLM matching requires OPENAI_API_KEY to be configured"
        )


def _response_text(response: Any) -> str:
    value = getattr(response, "output_text", None)
    if not isinstance(value, str) or not value.strip():
        raise LLMResponseError("OpenAI returned no text output")
    return value.strip()
