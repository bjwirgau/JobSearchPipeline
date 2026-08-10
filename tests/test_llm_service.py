"""Gemini and OpenAI LLM service tests without network access."""

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
    OpenAILLMConfig,
    OpenAILLMService,
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


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def create(self, **arguments: object) -> object:
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


class OpenAILLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_non_stored_structured_output_with_gpt_5_4(self) -> None:
        responses = FakeResponses(
            SimpleNamespace(output_text=json.dumps({"answers": [], "unresolved": []}))
        )
        service = OpenAILLMService(
            OpenAILLMConfig(
                api_key="secret-key",
                model="gpt-5.4",
                max_output_tokens=2_000,
            ),
            client=SimpleNamespace(responses=responses),
        )
        schema = {
            "type": "object",
            "properties": {
                "answers": {"type": "array", "items": {"type": "object"}},
                "unresolved": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["answers", "unresolved"],
            "additionalProperties": False,
        }

        result = await service.generate_structured("Fill fields", schema=schema)

        self.assertEqual(result, {"answers": [], "unresolved": []})
        request = responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.4")
        self.assertEqual(request["input"], "Fill fields")
        self.assertEqual(request["max_output_tokens"], 2_000)
        self.assertFalse(request["store"])
        response_format = request["text"]["format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(response_format["name"], "application_form_answers")
        self.assertTrue(response_format["strict"])
        self.assertEqual(response_format["schema"], schema)
        self.assertNotIn("secret-key", repr(service))

    async def test_redacts_openai_api_key_from_provider_errors(self) -> None:
        service = OpenAILLMService(
            OpenAILLMConfig(api_key="secret-key"),
            client=SimpleNamespace(
                responses=FakeResponses(RuntimeError("secret-key was rejected"))
            ),
        )

        with self.assertRaises(LLMResponseError) as raised:
            await service.generate_text("Fill fields")

        self.assertIn("OpenAI request failed", str(raised.exception))
        self.assertNotIn("secret-key", str(raised.exception))

    async def test_disabled_service_can_explain_openai_configuration(self) -> None:
        service = DisabledLLMService(
            "Application form filling requires OPENAI_API_KEY to be configured"
        )

        with self.assertRaisesRegex(LLMNotConfiguredError, "OPENAI_API_KEY"):
            await service.generate_structured("Fill fields", schema={"type": "object"})


if __name__ == "__main__":
    unittest.main()
