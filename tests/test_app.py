"""Application argument and search-criteria composition tests."""

from __future__ import annotations

import unittest

from app import (
    _arguments,
    _format_job_grid,
    _format_searched_sources,
    _search_criteria,
)
from config import Settings
from models import (
    CandidateProfile,
    JobPosting,
    MatchBreakdown,
    MatchResult,
    ResumeKnowledgeBase,
)


class ApplicationCriteriaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.from_env({"JOB_AGENT_REMOTE_COUNTRY": "US"})
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            desired_titles=("Software Engineer",),
            remote_preference="remote",
        )
        self.knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python",),
        )

    def test_configured_country_is_in_arguments_and_criteria(self) -> None:
        arguments = _arguments(["--search"], settings=self.settings)

        criteria = _search_criteria(arguments, self.candidate, self.knowledge)

        self.assertEqual(arguments.remote_country, "us")
        self.assertEqual(criteria.remote_country, "us")

    def test_cli_country_overrides_configured_country(self) -> None:
        arguments = _arguments(
            ["--search", "--remote-country", "ca"],
            settings=self.settings,
        )

        criteria = _search_criteria(arguments, self.candidate, self.knowledge)

        self.assertEqual(arguments.remote_country, "ca")
        self.assertEqual(criteria.remote_country, "ca")

    def test_search_results_render_as_a_named_column_grid(self) -> None:
        job = JobPosting(
            source="remotive",
            external_id="job-1",
            title="Senior Software Engineer for Distributed Systems",
            company="Example Company",
            url="https://example.com/jobs/senior-software-engineer",
            location="Remote - United States",
            salary_min=140000,
            salary_max=180000,
            salary_currency="USD",
            is_remote=True,
            remote_country_codes=("us",),
        )
        match = MatchResult(
            candidate_id="candidate-1",
            job_id=job.job_id,
            score=0.87,
            breakdown=MatchBreakdown(
                skills=0.9,
                title=0.8,
                location=1.0,
                experience=0.8,
            ),
        )

        grid = _format_job_grid(((job, match),))

        self.assertIn("| # | Match |", grid)
        self.assertIn("Title", grid)
        self.assertIn("Company", grid)
        self.assertIn("Location", grid)
        self.assertIn("Salary", grid)
        self.assertIn("Source", grid)
        self.assertIn("URL", grid)
        self.assertIn("87%", grid)
        self.assertIn("USD 140,000-180,000", grid)
        line_lengths = {len(line) for line in grid.splitlines()}
        self.assertEqual(len(line_lengths), 1)

    def test_all_selected_sources_are_displayed(self) -> None:
        output = _format_searched_sources(("adzuna", "remotive", "usajobs"))

        self.assertEqual(
            output,
            "Searching sources (3): adzuna, remotive, usajobs",
        )


if __name__ == "__main__":
    unittest.main()
