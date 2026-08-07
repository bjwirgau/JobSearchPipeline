"""OpenAI Responses API service tests without network access."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from services import (
    DisabledLLMService,
    LLMNotConfiguredError,
    LLMResponseError,
    OpenAIConfig,
    OpenAILLMService,
)


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def create(self, **arguments: object) -> object:
        self.calls.append(arguments)
        return self.output


class OpenAILLMServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_requests_strict_structured_output_without_storage(self) -> None:
        responses = FakeResponses(
            SimpleNamespace(output_text=json.dumps({"score": 0.8}))
        )
        service = OpenAILLMService(
            OpenAIConfig(
                api_key="secret-key",
                model="gpt-5.6-terra",
                reasoning_effort="low",
            ),
            client=SimpleNamespace(responses=responses),
        )
        schema = {
            "type": "object",
            "properties": {"score": {"type": "number"}},
            "required": ["score"],
            "additionalProperties": False,
        }

        result = await service.generate_structured("Evaluate this role", schema=schema)

        self.assertEqual(result, {"score": 0.8})
        request = responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.6-terra")
        self.assertEqual(request["reasoning"], {"effort": "low"})
        self.assertFalse(request["store"])
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(request["text"]["format"]["schema"], schema)
        self.assertNotIn("secret-key", repr(service))

    async def test_rejects_invalid_structured_json(self) -> None:
        service = OpenAILLMService(
            OpenAIConfig(api_key="secret-key"),
            client=SimpleNamespace(
                responses=FakeResponses(SimpleNamespace(output_text="not json"))
            ),
        )

        with self.assertRaisesRegex(LLMResponseError, "invalid structured JSON"):
            await service.generate_structured("Evaluate", schema={"type": "object"})

    async def test_disabled_service_explains_required_configuration(self) -> None:
        with self.assertRaisesRegex(LLMNotConfiguredError, "OPENAI_API_KEY"):
            await DisabledLLMService().generate_structured(
                "Evaluate",
                schema={"type": "object"},
            )


if __name__ == "__main__":
    unittest.main()
