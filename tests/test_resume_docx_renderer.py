"""Native Microsoft Word resume rendering tests."""

from __future__ import annotations

import unittest
from io import BytesIO
from zipfile import is_zipfile

try:
    from docx import Document
except ImportError:
    Document = None

from models import CandidateProfile, GeneratedResumeContent, ResumeKnowledgeBase
from services import ResumeDocxRenderer


class ResumeDocxRendererTests(unittest.TestCase):
    @unittest.skipIf(Document is None, "python-docx is not installed")
    def test_renders_editable_professional_word_document(self) -> None:
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            phone="(555) 123-4567",
            location="Denver, CO",
            skills=("Python", "SQL"),
        )
        knowledge = ResumeKnowledgeBase.from_dict(
            {
                "candidate_id": "candidate-1",
                "skills": ["Python", "SQL"],
                "roles": [
                    {
                        "company": "Example Corp",
                        "title": "Data Engineer",
                        "location": "Remote, US",
                        "start_date": "2022-01",
                        "end_date": "Present",
                        "responsibilities": ["Built reliable data pipelines."],
                    }
                ],
                "achievements": [
                    {
                        "category": "Reliability",
                        "description": "Improved platform reliability.",
                    }
                ],
                "education": [
                    {
                        "institution": "Example University",
                        "location": "Denver, CO",
                        "degree": "Bachelor of Science",
                        "field": "Computer Engineering",
                    }
                ],
                "certifications": [
                    {
                        "name": "Cloud Certification",
                        "issued": "2025-01",
                        "status": "Current",
                    }
                ],
            }
        )
        content = GeneratedResumeContent.from_dict(
            {
                "professional_summary": "Builds reliable data platforms.",
                "skills": ["Python", "SQL"],
                "experience": [
                    {
                        "company": "Example Corp",
                        "title": "Data Engineer",
                        "location": "Remote, US",
                        "start_date": "2022-01",
                        "end_date": "Present",
                        "responsibilities": ["Built reliable data pipelines."],
                    }
                ],
                "career_highlights": [
                    {
                        "category": "Reliability",
                        "description": "Improved platform reliability.",
                    }
                ],
                "education": [
                    {
                        "institution": "Example University",
                        "location": "Denver, CO",
                        "degree": "Bachelor of Science",
                        "field": "Computer Engineering",
                        "status": None,
                    }
                ],
                "certifications": [
                    {
                        "name": "Cloud Certification",
                        "issued": "2025-01",
                        "status": "Current",
                    }
                ],
            }
        )
        content.validate_against(knowledge, candidate_skills=candidate.skills)

        rendered = ResumeDocxRenderer().render(
            candidate,
            content,
            target_title="Senior Data Engineer",
        )

        self.assertTrue(is_zipfile(BytesIO(rendered)))
        assert Document is not None
        document = Document(BytesIO(rendered))
        text = "\n".join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn("Example Candidate", text)
        self.assertIn("candidate@example.com", text)
        self.assertIn("(555) 123-4567", text)
        self.assertIn("Senior Data Engineer — Builds reliable data platforms.", text)
        self.assertIn("PROFESSIONAL EXPERIENCE", text)
        self.assertIn("Remote, US", text)
        self.assertIn("January 2022 – Present", text)
        self.assertIn("Built reliable data pipelines.", text)
        self.assertIn("Improved platform reliability.", text)
        self.assertIn("Bachelor of Science in Computer Engineering", text)
        self.assertIn("Cloud Certification", text)
        self.assertIn("Issued January 2025", text)
        self.assertEqual(
            document.core_properties.title,
            "Example Candidate - Senior Data Engineer Resume",
        )
        self.assertAlmostEqual(document.sections[0].top_margin.inches, 0.55, places=2)


if __name__ == "__main__":
    unittest.main()
