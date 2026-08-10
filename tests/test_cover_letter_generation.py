"""Evidence validation and one-page cover-letter rendering tests."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping
from zipfile import is_zipfile

from agents import CoverLetterGenerationAgent
from models import (
    COVER_LETTER_MAX_WORDS,
    CandidateProfile,
    GeneratedCoverLetterContent,
    InvalidGeneratedCoverLetterError,
    JobPosting,
    ResumeKnowledgeBase,
)
from services import (
    CoverLetterDocxRenderer,
    CoverLetterHTMLRenderer,
    DocumentService,
)


PROMPT = """\
CANDIDATE\n{candidate_profile}\nKNOWLEDGE\n{resume_knowledge}\nJOB\n{job_posting}
"""


class StaticCoverLetterGenerator:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    async def generate_cover_letter(
        self,
        prompt: str,
        *,
        model: str,
    ) -> Mapping[str, Any]:
        self.calls.append((prompt, model))
        return self.response


def _response(*, middle: str = "I built reliable Python data pipelines.") -> dict:
    return {
        "paragraphs": [
            {
                "text": (
                    "I am applying for the Senior Data Engineer role at "
                    "Target & Company."
                ),
                "evidence_ids": ["job.title", "job.company"],
            },
            {
                "text": middle,
                "evidence_ids": ["resume.role.0"],
            },
            {
                "text": "I welcome the opportunity to discuss this role.",
                "evidence_ids": ["job.title"],
            },
        ]
    }


class CoverLetterGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example <Candidate>",
            email="candidate@example.com",
            phone="(555) 123-4567",
            location="Denver, CO",
            linkedin_url="https://linkedin.com/in/example",
            website_url="https://example.dev/?source=cover&letter=1",
            skills=("Python", "SQL"),
            resume_path="/private/source-resume.pdf",
        )
        self.knowledge = ResumeKnowledgeBase.from_dict(
            {
                "candidate_id": "candidate-1",
                "skills": ["Python", "SQL"],
                "roles": [
                    {
                        "company": "Example Corp",
                        "title": "Data Engineer",
                        "start_date": "2022-01",
                        "end_date": "Present",
                        "responsibilities": [
                            "Built reliable Python data pipelines."
                        ],
                    }
                ],
            }
        )
        self.job = JobPosting(
            source="greenhouse",
            external_id="job-1",
            title="Senior Data Engineer",
            company="Target & Company",
            url="https://example.com/jobs/1",
            location="Remote, US",
            description="Build reliable data systems with Python and SQL.",
            skills=("Python", "SQL"),
            raw={"private_payload": "must not be sent"},
        )

    async def test_generates_grounded_print_ready_html_without_sending_contact(self) -> None:
        generator = StaticCoverLetterGenerator(_response())
        with tempfile.TemporaryDirectory() as directory:
            agent = CoverLetterGenerationAgent(
                generator=generator,  # type: ignore[arg-type]
                documents=DocumentService(directory),
                prompt_template=PROMPT,
            )

            artifacts = await agent.generate(
                candidate=self.candidate,
                knowledge=self.knowledge,
                job=self.job,
                model="gpt-5.4",
            )

            self.assertEqual(len(generator.calls), 1)
            prompt, model = generator.calls[0]
            self.assertEqual(model, "gpt-5.4")
            self.assertIn('"resume.role.0"', prompt)
            self.assertIn('"job.company": "Target & Company"', prompt)
            self.assertNotIn("Example <Candidate>", prompt)
            self.assertNotIn("candidate@example.com", prompt)
            self.assertNotIn("/private/source-resume.pdf", prompt)
            self.assertNotIn("private_payload", prompt)

            self.assertEqual(len(artifacts), 1)
            path = Path(artifacts[0].path)
            self.assertEqual(path.suffix, ".html")
            document = path.read_text(encoding="utf-8")
            self.assertIn("@page { size: Letter", document)
            self.assertIn("Example &lt;Candidate&gt;", document)
            self.assertIn("Dear Target &amp; Company Hiring Team,", document)
            self.assertIn("I built reliable Python data pipelines.", document)
            self.assertNotIn("evidence_ids", document)
            self.assertNotIn("<Candidate>", document)

    async def test_rejects_unknown_evidence_and_more_than_350_words(self) -> None:
        unknown = _response()
        unknown["paragraphs"][1]["evidence_ids"] = ["resume.role.99"]
        with tempfile.TemporaryDirectory() as directory:
            agent = CoverLetterGenerationAgent(
                generator=StaticCoverLetterGenerator(unknown),  # type: ignore[arg-type]
                documents=DocumentService(directory),
                prompt_template=PROMPT,
            )
            with self.assertRaisesRegex(
                InvalidGeneratedCoverLetterError,
                "unknown evidence IDs",
            ):
                await agent.generate(
                    candidate=self.candidate,
                    knowledge=self.knowledge,
                    job=self.job,
                    model="gpt-5.4",
                )

        too_long = _response(middle="supported " * COVER_LETTER_MAX_WORDS)
        with self.assertRaisesRegex(
            InvalidGeneratedCoverLetterError,
            "350-word",
        ):
            GeneratedCoverLetterContent.from_dict(too_long)

    @unittest.skipUnless(
        importlib.util.find_spec("docx"),
        "python-docx is not installed",
    )
    def test_renders_an_editable_word_cover_letter(self) -> None:
        from docx import Document

        content = GeneratedCoverLetterContent.from_dict(_response())
        rendered = CoverLetterDocxRenderer().render(
            self.candidate,
            content,
            job=self.job,
            generated_on=date(2026, 8, 10),
        )

        self.assertTrue(is_zipfile(BytesIO(rendered)))
        document = Document(BytesIO(rendered))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("August 10, 2026", text)
        self.assertIn("Dear Target & Company Hiring Team,", text)
        self.assertIn("I built reliable Python data pipelines.", text)
        self.assertEqual(
            document.core_properties.subject,
            "Application for Senior Data Engineer",
        )

    def test_html_renderer_uses_a_fixed_letter_page(self) -> None:
        content = GeneratedCoverLetterContent.from_dict(_response())
        document = CoverLetterHTMLRenderer().render(
            self.candidate,
            content,
            job=self.job,
            generated_on=date(2026, 8, 10),
        )

        self.assertIn("August 10, 2026", document)
        self.assertIn("width: min(8.5in, 100%);", document)
        self.assertLessEqual(content.word_count, COVER_LETTER_MAX_WORDS)
