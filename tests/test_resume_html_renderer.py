"""Professional resume HTML rendering and evidence validation tests."""

from __future__ import annotations

import unittest

from models import (
    CandidateProfile,
    GeneratedResumeContent,
    InvalidGeneratedResumeError,
    ResumeCertification,
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
            phone="(555) 123-4567",
            location="Denver & Remote",
            linkedin_url="https://www.linkedin.com/in/example-candidate",
            github_url="https://github.com/example-candidate",
            website_url="https://example.dev/?from=resume&format=html",
            skills=("Python", "SQL"),
        )
        self.knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python", "SQL"),
            roles=(
                ResumeRole(
                    company="Example Corp",
                    title="Data Engineer",
                    location="Remote, US",
                    start_date="2022-01",
                    end_date="Present",
                    responsibilities=("Built reliable pipelines.",),
                ),
            ),
            achievements=("Improved platform reliability.",),
            education=("B.S. Computer Engineering",),
            certifications=(
                ResumeCertification(
                    name="Cloud Certification",
                    issued="2025-01",
                    status="Current",
                ),
            ),
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
                        "location": "Remote, US",
                        "start_date": "2022-01",
                        "end_date": "Present",
                        "responsibilities": ["Built reliable pipelines."],
                    }
                ],
                "career_highlights": ["Improved platform reliability."],
                "education": ["B.S. Computer Engineering"],
                "certifications": [
                    {
                        "name": "Cloud Certification",
                        "issued": "2025-01",
                        "status": "Current",
                    }
                ],
            }
        )
        content.validate_against(
            self.knowledge,
            candidate_skills=self.candidate.skills,
        )

        document = ResumeHTMLRenderer().render(
            self.candidate,
            content,
            target_title="Senior Data Engineer <Lead>",
        )

        self.assertTrue(document.startswith("<!doctype html>"))
        self.assertIn("<style>", document)
        self.assertIn("@page { size: Letter", document)
        self.assertIn("@media print", document)
        self.assertIn("Example &lt;Candidate&gt;", document)
        self.assertIn("(555) 123-4567", document)
        self.assertIn("Denver &amp; Remote", document)
        self.assertIn(
            'href="https://www.linkedin.com/in/example-candidate">'
            "linkedin.com/in/example-candidate</a>",
            document,
        )
        self.assertIn(
            'href="https://github.com/example-candidate">'
            "github.com/example-candidate</a>",
            document,
        )
        self.assertIn(
            'href="https://example.dev/?from=resume&amp;format=html">'
            "example.dev/?from=resume&amp;format=html</a>",
            document,
        )
        self.assertIn(
            '<span class="summary-title">Senior Data Engineer &lt;Lead&gt;</span>'
            " — Engineering &lt;script&gt;",
            document,
        )
        self.assertIn('<h3 class="role-title">Data Engineer</h3>', document)
        self.assertEqual(document.count("font-weight: 700;"), 1)
        self.assertNotIn("<strong", document)
        self.assertIn("Remote, US", document)
        self.assertIn("January 2022 – Present", document)
        self.assertIn("Issued January 2025", document)
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

        unsupported_responsibility = GeneratedResumeContent.from_dict(
            {
                "professional_summary": "Data engineer.",
                "skills": [],
                "experience": [
                    {
                        "company": "Example Corp",
                        "title": "Data Engineer",
                        "location": "Remote, US",
                        "start_date": "2022-01",
                        "end_date": "Present",
                        "responsibilities": ["Invented an unsupported achievement."],
                    }
                ],
                "career_highlights": [],
                "education": [],
                "certifications": [],
            }
        )
        with self.assertRaisesRegex(
            InvalidGeneratedResumeError,
            "unsupported responsibilities",
        ):
            unsupported_responsibility.validate_against(self.knowledge)


if __name__ == "__main__":
    unittest.main()
