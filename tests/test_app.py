"""Application argument and search-criteria composition tests."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr

from app import (
    _arguments,
    _format_apify_dry_run,
    _format_company_grid,
    _format_job_grid,
    _format_search_job_grid,
    _format_searched_sources,
    _search_criteria,
)
from config import Settings
from models import (
    CandidateProfile,
    CompanyProspect,
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

    def test_apify_dry_run_prints_actor_input(self) -> None:
        arguments = _arguments(
            [
                "--search",
                "--dry-run",
                "--source",
                "linkedin",
                "--requirement",
                "AWS",
                "--limit",
                "10",
            ],
            settings=self.settings,
        )
        criteria = _search_criteria(arguments, self.candidate, self.knowledge)

        output = _format_apify_dry_run(
            criteria,
            actor_id="automation-lab/linkedin-jobs-scraper",
        )

        self.assertTrue(arguments.dry_run)
        self.assertIn("Apify dry run: no requests sent.", output)
        self.assertIn("Queries: 1", output)
        self.assertIn('"searchQuery": "Software Engineer AWS"', output)
        self.assertIn('"maxJobs": 10', output)
        self.assertIn('"workplaceType": "2"', output)
        self.assertNotIn("api-token", output)

    def test_apify_dry_run_rejects_non_linkedin_sources(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--search", "--dry-run", "--source", "remotive"],
                settings=self.settings,
            )

        self.assertIn(
            "--dry-run supports only the linkedin source",
            errors.getvalue(),
        )

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

        search_grid = _format_search_job_grid((job,))
        self.assertIn("Title", search_grid)
        self.assertIn("Posted", search_grid)
        self.assertNotIn("Match", search_grid)

    def test_all_selected_sources_are_displayed(self) -> None:
        output = _format_searched_sources(("adzuna", "remotive", "usajobs"))

        self.assertEqual(
            output,
            "Searching sources (3): adzuna, remotive, usajobs",
        )

    def test_company_crawler_command_is_separate_from_job_search(self) -> None:
        arguments = _arguments(
            ["--crawl-greenhouse-companies", "--crawl-limit", "50"],
            settings=self.settings,
        )

        self.assertTrue(arguments.crawl_greenhouse_companies)
        self.assertEqual(arguments.crawl_limit, 50)
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--search", "--crawl-greenhouse-companies"],
                settings=self.settings,
            )
        self.assertIn("cannot be combined", errors.getvalue())

    def test_prospect_matching_is_a_separate_rate_limited_command(self) -> None:
        arguments = _arguments(
            ["--match-prospects", "--match-limit", "15"],
            settings=self.settings,
        )

        self.assertTrue(arguments.match_prospects)
        self.assertEqual(arguments.match_limit, 15)
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(["--search", "--match-prospects"], settings=self.settings)
        self.assertIn("cannot be combined", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--match-prospects", "--match-limit", "16"],
                settings=self.settings,
            )
        self.assertIn("between 1 and 15", errors.getvalue())

    def test_resume_generation_accepts_one_job_id_as_a_separate_command(self) -> None:
        arguments = _arguments(
            ["--generate-resume", "job-123", "--resume-format", "both"],
            settings=self.settings,
        )

        self.assertEqual(arguments.generate_resume, "job-123")
        self.assertEqual(arguments.resume_format, "both")
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--generate-resume", "job-123", "--search"],
                settings=self.settings,
            )
        self.assertIn("cannot be combined", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(["--resume-format", "docx"], settings=self.settings)
        self.assertIn("requires --generate-resume", errors.getvalue())

    def test_matched_resume_generation_is_a_bounded_separate_command(self) -> None:
        arguments = _arguments(
            [
                "--generate-matched-resumes",
                "--resume-limit",
                "5",
                "--resume-format",
                "docx",
            ],
            settings=self.settings,
        )

        self.assertTrue(arguments.generate_matched_resumes)
        self.assertEqual(arguments.resume_limit, 5)
        self.assertEqual(arguments.resume_format, "docx")

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--generate-matched-resumes", "--generate-resume", "job-123"],
                settings=self.settings,
            )
        self.assertIn("cannot be combined", errors.getvalue())

        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--generate-matched-resumes", "--resume-limit", "101"],
                settings=self.settings,
            )
        self.assertIn("between 1 and 100", errors.getvalue())

    def test_greenhouse_board_limit_is_configurable_and_validated(self) -> None:
        arguments = _arguments(
            ["--search", "--greenhouse-board-limit", "10"],
            settings=self.settings,
        )

        self.assertEqual(arguments.greenhouse_board_limit, 10)
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit):
            _arguments(
                ["--search", "--greenhouse-board-limit", "1001"],
                settings=self.settings,
            )
        self.assertIn("between 1 and 1000", errors.getvalue())

    def test_company_crawler_results_render_as_a_named_grid(self) -> None:
        grid = _format_company_grid(
            (
                CompanyProspect.from_board(
                    company_name="Example Company",
                    board_token="example",
                    company_url="https://job-boards.greenhouse.io/example",
                ),
            )
        )

        self.assertIn("Company", grid)
        self.assertIn("Board token", grid)
        self.assertIn("Company URL", grid)
        self.assertIn("Example Company", grid)
        self.assertEqual(len({len(line) for line in grid.splitlines()}), 1)


if __name__ == "__main__":
    unittest.main()
