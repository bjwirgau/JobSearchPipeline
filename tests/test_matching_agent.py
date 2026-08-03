"""Matching-agent scoring tests."""

from __future__ import annotations

import unittest

from agents import MatchingAgent
from models import CandidateProfile, JobPosting


class MatchingAgentTests(unittest.TestCase):
    def test_scores_each_component_transparently(self) -> None:
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            skills=("Python", "SQL"),
            years_experience=4,
            desired_titles=("Data Engineer",),
            desired_locations=("Denver, CO",),
        )
        job = JobPosting(
            source="sample",
            external_id="job-1",
            title="Senior Data Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            location="Denver, CO",
            skills=("Python", "SQL", "AWS"),
            requirements=("5+ years of relevant experience",),
        )

        result = MatchingAgent().score(candidate, job)

        self.assertAlmostEqual(result.breakdown.skills, 2 / 3)
        self.assertAlmostEqual(result.breakdown.title, 2 / 3)
        self.assertEqual(result.breakdown.location, 1.0)
        self.assertEqual(result.breakdown.experience, 0.8)
        self.assertAlmostEqual(result.score, 0.73)
        self.assertEqual(result.matched_skills, ("Python", "SQL"))
        self.assertEqual(result.missing_skills, ("AWS",))


if __name__ == "__main__":
    unittest.main()
