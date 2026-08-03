"""Parser-agent behavior tests."""

from __future__ import annotations

import unittest

from agents import ParserAgent
from models import JobPosting


class ParserAgentTests(unittest.TestCase):
    def test_extracts_sections_and_known_skills(self) -> None:
        job = JobPosting(
            source="sample",
            external_id="1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            description=(
                "Responsibilities:\n"
                "- Build Python data services.\n"
                "- Maintain pipelines.\n"
                "Requirements:\n"
                "- Strong SQL skills.\n"
                "- Experience with Docker."
            ),
        )

        parsed = ParserAgent().parse(job)

        self.assertEqual(
            parsed.responsibilities,
            ("Build Python data services.", "Maintain pipelines."),
        )
        self.assertEqual(
            parsed.requirements,
            ("Strong SQL skills.", "Experience with Docker."),
        )
        self.assertEqual(parsed.skills, ("Python", "SQL", "Docker"))


if __name__ == "__main__":
    unittest.main()
