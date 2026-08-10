"""OpenAI resume-generation service tests without network access."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from services import (
    CoverLetterGenerationResponseError,
    DisabledResumeGenerator,
    OpenAIResumeConfig,
    OpenAIResumeGenerator,
    ResumeGenerationNotConfiguredError,
    ResumeGenerationResponseError,
)


class FakeResponses:
    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    def create(self, **arguments: object) -> object:
        self.calls.append(arguments)
        if isinstance(self.output, Exception):
            raise self.output
        return self.output


class OpenAIResumeGeneratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_generates_one_non_stored_response_with_selected_model(self) -> None:
        resume = {
            "target_title": None,
            "professional_summary": "Builds reliable data platforms.",
            "skills": ["Python"],
            "experience": [],
            "career_highlights": [],
            "education": [],
            "certifications": [],
        }
        responses = FakeResponses(SimpleNamespace(output_text=json.dumps(resume)))
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(
                api_key="secret-key",
                max_output_tokens=4_000,
            ),
            client=SimpleNamespace(responses=responses),
        )

        result = await generator.generate_resume("Candidate evidence", model="gpt-5.4")

        self.assertEqual(result, resume)
        self.assertEqual(len(responses.calls), 1)
        request = responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.4")
        self.assertEqual(request["input"], "Candidate evidence")
        self.assertEqual(request["max_output_tokens"], 4_000)
        self.assertFalse(request["store"])
        response_format = request["text"]["format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["strict"])
        self.assertIn("target_title", response_format["schema"]["required"])
        self.assertIn("professional_summary", response_format["schema"]["required"])
        properties = response_format["schema"]["properties"]
        self.assertEqual(properties["target_title"]["type"], ["string", "null"])
        experience_properties = properties["experience"]["items"]["properties"]
        self.assertIn("location", experience_properties)
        self.assertIn("responsibilities", experience_properties)
        self.assertEqual(properties["career_highlights"]["items"]["type"], "object")
        self.assertEqual(properties["education"]["items"]["type"], "object")
        self.assertEqual(properties["certifications"]["items"]["type"], "object")
        self.assertIn("Never invent", request["instructions"])
        self.assertIn("do not copy original_title", request["instructions"])
        self.assertNotIn("secret-key", repr(generator))

    async def test_redacts_api_key_from_provider_errors(self) -> None:
        responses = FakeResponses(RuntimeError("request with secret-key failed"))
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(api_key="secret-key"),
            client=SimpleNamespace(responses=responses),
        )

        with self.assertRaises(ResumeGenerationResponseError) as raised:
            await generator.generate_resume("Evidence", model="gpt-5.4")

        self.assertIn("RuntimeError", str(raised.exception))
        self.assertNotIn("secret-key", str(raised.exception))

    async def test_generates_non_stored_evidence_linked_cover_letter(self) -> None:
        cover_letter = {
            "paragraphs": [
                {
                    "text": "I am applying for the role at Example.",
                    "evidence_ids": ["job.title", "job.company"],
                },
                {
                    "text": "I build reliable systems.",
                    "evidence_ids": ["resume.role.0"],
                },
                {
                    "text": "I welcome a conversation.",
                    "evidence_ids": ["job.title"],
                },
            ]
        }
        responses = FakeResponses(
            SimpleNamespace(output_text=json.dumps(cover_letter))
        )
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(api_key="secret-key", max_output_tokens=2_000),
            client=SimpleNamespace(responses=responses),
        )

        result = await generator.generate_cover_letter(
            "Evidence map",
            model="gpt-5.4",
        )

        self.assertEqual(result, cover_letter)
        request = responses.calls[0]
        self.assertEqual(request["model"], "gpt-5.4")
        self.assertEqual(request["input"], "Evidence map")
        self.assertFalse(request["store"])
        response_format = request["text"]["format"]
        self.assertEqual(response_format["name"], "tailored_cover_letter")
        self.assertTrue(response_format["strict"])
        paragraphs = response_format["schema"]["properties"]["paragraphs"]
        self.assertEqual(paragraphs["maxItems"], 4)
        self.assertIn("evidence_ids", paragraphs["items"]["properties"])
        self.assertIn("only the supplied evidence", request["instructions"])
        self.assertIn("no more than 350 words", request["instructions"])

    async def test_redacts_key_from_cover_letter_errors(self) -> None:
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(api_key="secret-key"),
            client=SimpleNamespace(
                responses=FakeResponses(RuntimeError("secret-key failed"))
            ),
        )

        with self.assertRaises(CoverLetterGenerationResponseError) as raised:
            await generator.generate_cover_letter("Evidence", model="gpt-5.4")

        self.assertNotIn("secret-key", str(raised.exception))

    async def test_rejects_empty_response(self) -> None:
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(api_key="secret-key"),
            client=SimpleNamespace(
                responses=FakeResponses(SimpleNamespace(output_text="  "))
            ),
        )

        with self.assertRaisesRegex(ResumeGenerationResponseError, "no text output"):
            await generator.generate_resume("Evidence", model="gpt-5.4")

    async def test_rejects_invalid_structured_json(self) -> None:
        generator = OpenAIResumeGenerator(
            OpenAIResumeConfig(api_key="secret-key"),
            client=SimpleNamespace(
                responses=FakeResponses(SimpleNamespace(output_text="not json"))
            ),
        )

        with self.assertRaisesRegex(
            ResumeGenerationResponseError,
            "invalid structured JSON",
        ):
            await generator.generate_resume("Evidence", model="gpt-5.4")

    async def test_disabled_generator_explains_required_configuration(self) -> None:
        with self.assertRaisesRegex(
            ResumeGenerationNotConfiguredError,
            "OPENAI_API_KEY",
        ):
            await DisabledResumeGenerator().generate_resume(
                "Evidence",
                model="gpt-5.4",
            )
        with self.assertRaisesRegex(
            ResumeGenerationNotConfiguredError,
            "OPENAI_API_KEY",
        ):
            await DisabledResumeGenerator().generate_cover_letter(
                "Evidence",
                model="gpt-5.4",
            )


if __name__ == "__main__":
    unittest.main()
