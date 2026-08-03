"""Matching-agent scoring tests."""

from __future__ import annotations

import unittest

from agents import MatchingAgent
from models import CandidateProfile, JobPosting, ResumeKnowledgeBase


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

    def test_uses_resume_skill_years_and_industries_as_evidence(self) -> None:
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            skills=("SQL",),
            years_experience=2,
            desired_titles=("Magento Engineer",),
            remote_preference="flexible",
        )
        knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Magento", "PHP", "AWS"),
            years={"Magento": 10, "PHP": 10},
            industries=("Ecommerce", "Retail"),
        )
        job = JobPosting(
            source="sample",
            external_id="job-2",
            title="Senior Magento Engineer",
            company="Example",
            url="https://example.com/jobs/2",
            is_remote=True,
            skills=("Magento", "PHP", "AWS"),
            industries=("Ecommerce",),
            requirements=("8+ years of relevant experience",),
        )

        result = MatchingAgent().score(candidate, job, knowledge)

        self.assertEqual(result.breakdown.skills, 1.0)
        self.assertEqual(result.breakdown.experience, 1.0)
        self.assertEqual(result.breakdown.industry, 1.0)
        self.assertEqual(result.skill_years, {"Magento": 10, "PHP": 10})
        self.assertEqual(result.missing_skills, ())
        self.assertAlmostEqual(result.score, 0.925)


if __name__ == "__main__":
    unittest.main()
