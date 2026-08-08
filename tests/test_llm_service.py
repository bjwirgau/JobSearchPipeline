"""Gemini API service tests without network access."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from services import (
    DisabledLLMService,
    GeminiConfig,
    GeminiLLMService,
    LLMNotConfiguredError,
    LLMResponseError,
)


class FakeModels:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def generate_content(self, **arguments: object) -> object:
        self.calls.append(arguments)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class GeminiLLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_structured_json_output(self) -> None:
        models = FakeModels(SimpleNamespace(text=json.dumps({"score": 0.8})))
        service = GeminiLLMService(
            GeminiConfig(
                api_key="secret-key",
                model="gemini-3.5-flash-lite",
            ),
            client=SimpleNamespace(models=models),
        )
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
            "additionalProperties": False,
        }

        result = await service.generate_structured("Evaluate this role", schema=schema)

        self.assertEqual(result, {"score": 0.8})
        request = models.calls[0]
        self.assertEqual(request["model"], "gemini-3.5-flash-lite")
        self.assertEqual(request["contents"], "Evaluate this role")
        self.assertEqual(request["config"]["response_mime_type"], "application/json")
        self.assertEqual(request["config"]["response_json_schema"], schema)
        self.assertNotIn("secret-key", repr(service))

    async def test_rejects_invalid_structured_json(self) -> None:
        service = GeminiLLMService(
            GeminiConfig(api_key="secret-key"),
            client=SimpleNamespace(models=FakeModels(SimpleNamespace(text="not json"))),
        )

        with self.assertRaisesRegex(LLMResponseError, "invalid structured JSON"):
            await service.generate_structured("Evaluate", schema={"type": "object"})

    async def test_redacts_api_key_from_provider_errors(self) -> None:
        service = GeminiLLMService(
            GeminiConfig(api_key="secret-key"),
            client=SimpleNamespace(
                models=FakeModels(RuntimeError("request with secret-key failed"))
            ),
        )

        with self.assertRaises(LLMResponseError) as raised:
            await service.generate_text("Evaluate")

        self.assertIn("RuntimeError", str(raised.exception))
        self.assertNotIn("secret-key", str(raised.exception))

    async def test_spaces_requests_to_respect_fifteen_per_minute(self) -> None:
        models = FakeModels(SimpleNamespace(text="ok"))
        now = [100.0]
        delays: list[float] = []

        async def advance_clock(delay: float) -> None:
            delays.append(delay)
            now[0] += delay

        service = GeminiLLMService(
            GeminiConfig(api_key="secret-key"),
            client=SimpleNamespace(models=models),
            clock=lambda: now[0],
            sleep=advance_clock,
        )

        await service.generate_text("First")
        await service.generate_text("Second")

        self.assertEqual(len(models.calls), 2)
        self.assertEqual(delays, [4.0])

    async def test_disabled_service_explains_required_configuration(self) -> None:
        with self.assertRaisesRegex(LLMNotConfiguredError, "GEMINI_API_KEY"):
            await DisabledLLMService().generate_structured(
                "Evaluate",
                schema={"type": "object"},
            )


if __name__ == "__main__":
    unittest.main()
