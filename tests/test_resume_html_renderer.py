"""Professional resume HTML rendering and evidence validation tests."""

from __future__ import annotations

import unittest

from models import (
    CandidateProfile,
    GeneratedResumeContent,
    InvalidGeneratedResumeError,
    ResumeKnowledgeBase,
    ResumeRole,
)
from services import ResumeHTMLRenderer


class ResumeHTMLRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example <Candidate>",
            email="candidate@example.com",
            location="Denver & Remote",
            skills=("Python", "SQL"),
        )
        self.knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python", "SQL"),
            roles=(
                ResumeRole(
                    company="Example Corp",
                    title="Data Engineer",
                    start_date="2022",
                    end_date="Present",
                    achievements=("Built reliable pipelines.",),
                ),
            ),
            education=("B.S. Computer Engineering",),
            certifications=("Cloud Certification",),
        )

    def test_renders_standalone_print_ready_html_and_escapes_values(self) -> None:
        content = GeneratedResumeContent.from_dict(
            {
                "professional_summary": "Engineering <script>alert(1)</script>",
                "skills": ["Python", "SQL"],
                "experience": [
                    {
                        "company": "Example Corp",
                        "title": "Data Engineer",
                        "start_date": "2022",
                        "end_date": "Present",
                        "achievements": ["Built reliable pipelines."],
                    }
                ],
                "career_highlights": ["Improved platform reliability."],
                "education": ["B.S. Computer Engineering"],
                "certifications": ["Cloud Certification"],
            }
        )
        content.validate_against(
            self.knowledge,
            candidate_skills=self.candidate.skills,
        )

        document = ResumeHTMLRenderer().render(self.candidate, content)

        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertIn("<style>", document)
        self.assertIn("@page { size: Letter", document)
        self.assertIn("@media print", document)
        self.assertIn("Example &lt;Candidate&gt;", document)
        self.assertIn("Denver &amp; Remote", document)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", document)
        self.assertNotIn("<script>", document)
        self.assertNotIn("src=", document)

    def test_rejects_unsupported_generated_facts(self) -> None:
        unsupported_skill = GeneratedResumeContent.from_dict(
            {
                "professional_summary": "Data engineer.",
                "skills": ["Rust"],
                "experience": [],
                "career_highlights": [],
                "education": [],
                "certifications": [],
            }
        )
        with self.assertRaisesRegex(
            InvalidGeneratedResumeError,
            "unsupported skills: Rust",
        ):
            unsupported_skill.validate_against(self.knowledge)

        unsupported_role = GeneratedResumeContent.from_dict(
            {
                "professional_summary": "Data engineer.",
                "skills": [],
                "experience": [
                    {
                        "company": "Invented Corp",
                        "title": "CTO",
                        "start_date": None,
                        "end_date": None,
                        "achievements": [],
                    }
                ],
                "career_highlights": [],
                "education": [],
                "certifications": [],
            }
        )
        with self.assertRaisesRegex(
            InvalidGeneratedResumeError,
            "unsupported experience entry",
        ):
            unsupported_role.validate_against(self.knowledge)


if __name__ == "__main__":
    unittest.main()
