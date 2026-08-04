"""Application argument and search-criteria composition tests."""

from __future__ import annotations

import unittest

from app import _arguments, _search_criteria
from config import Settings
from models import CandidateProfile, ResumeKnowledgeBase


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


if __name__ == "__main__":
    unittest.main()
