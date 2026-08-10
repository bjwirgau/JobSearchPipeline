"""Language-model boundary with Gemini and OpenAI implementations."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping, Protocol


GEMINI_REQUESTS_PER_MINUTE = 15


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

    def __init__(
        self,
        config: GeminiConfig,
        *,
        client: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
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
        self._clock = clock
        self._sleep = sleep
        self._request_interval_seconds = 60 / GEMINI_REQUESTS_PER_MINUTE
        self._last_request_started: float | None = None
        self._rate_limit_lock = asyncio.Lock()

    async def generate_text(self, prompt: str) -> str:
        await self._wait_for_request_slot()
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
        await self._wait_for_request_slot()
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

    async def _wait_for_request_slot(self) -> None:
        async with self._rate_limit_lock:
            now = self._clock()
            if self._last_request_started is not None:
                delay = self._request_interval_seconds - (
                    now - self._last_request_started
                )
                if delay > 0:
                    await self._sleep(delay)
            self._last_request_started = self._clock()

    def _request_error(self, error: Exception) -> str:
        detail = str(error).strip().replace(self._config.api_key, "[REDACTED]")
        suffix = f": {detail}" if detail else ""
        return f"Gemini request failed: {type(error).__name__}{suffix}"


@dataclass(frozen=True, slots=True)
class OpenAILLMConfig:
    api_key: str = field(repr=False)
    model: str = "gpt-5.4"
    timeout_seconds: float = 60.0
    max_output_tokens: int = 1_500

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if not self.model.strip():
            raise ValueError("OpenAI model must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be greater than zero")
        if self.max_output_tokens <= 0:
            raise ValueError("OpenAI max output tokens must be greater than zero")


class OpenAILLMService:
    """Generate non-stored text or schema-constrained output with Responses."""

    def __init__(
        self,
        config: OpenAILLMConfig,
        *,
        client: Any | None = None,
    ) -> None:
        self._config = config
        self._client = client

    def _configured_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as error:
                raise LLMNotConfiguredError(
                    "install OpenAI support with: pip install -e ."
                ) from error
            self._client = OpenAI(
                api_key=self._config.api_key,
                timeout=self._config.timeout_seconds,
            )
        return self._client

    async def generate_text(self, prompt: str) -> str:
        response = await self._create_response(prompt)
        return _openai_response_text(response)

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        response = await self._create_response(
            prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "application_form_answers",
                    "strict": True,
                    "schema": dict(schema),
                }
            },
        )
        raw_text = _openai_response_text(response)
        try:
            value = json.loads(raw_text)
        except json.JSONDecodeError as error:
            raise LLMResponseError(
                "OpenAI returned invalid structured JSON"
            ) from error
        if not isinstance(value, Mapping):
            raise LLMResponseError("OpenAI structured output must be an object")
        return value

    async def _create_response(
        self,
        prompt: str,
        *,
        text: Mapping[str, Any] | None = None,
    ) -> Any:
        client = self._configured_client()
        arguments: dict[str, Any] = {
            "model": self._config.model,
            "input": prompt,
            "max_output_tokens": self._config.max_output_tokens,
            "store": False,
        }
        if text is not None:
            arguments["text"] = dict(text)
        try:
            return await asyncio.to_thread(client.responses.create, **arguments)
        except Exception as error:
            detail = str(error).strip().replace(
                self._config.api_key,
                "[REDACTED]",
            )
            suffix = f": {detail}" if detail else ""
            raise LLMResponseError(
                f"OpenAI request failed: {type(error).__name__}{suffix}"
            ) from error


class DisabledLLMService:
    def __init__(
        self,
        message: str = "LLM matching requires GEMINI_API_KEY to be configured",
    ) -> None:
        self._message = message

    async def generate_text(self, prompt: str) -> str:
        raise LLMNotConfiguredError(self._message)

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        raise LLMNotConfiguredError(self._message)


def _response_text(response: Any, *, provider: str) -> str:
    value = getattr(response, "text", None)
    if not isinstance(value, str) or not value.strip():
        raise LLMResponseError(f"{provider} returned no text output")
    return value.strip()


def _openai_response_text(response: Any) -> str:
    value = getattr(response, "output_text", None)
    if not isinstance(value, str) or not value.strip():
        raise LLMResponseError("OpenAI returned no text output")
    return value.strip()
