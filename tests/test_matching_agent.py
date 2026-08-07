"""LLM matching-agent tests."""

from __future__ import annotations

import unittest
from typing import Any, Mapping

from agents import InvalidMatchResponseError, MatchingAgent
from models import CandidateProfile, JobPosting, ResumeKnowledgeBase


PROMPT = """CANDIDATE:
{candidate_profile}
RESUME:
{resume_knowledge}
JOB:
{job_posting}
"""


class FakeLLMService:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def generate_text(self, prompt: str) -> str:
        raise AssertionError("matching must request structured output")

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((prompt, schema))
        return self.response


def match_response(**overrides: object) -> dict[str, Any]:
    response: dict[str, Any] = {
        "score": 0.82,
        "breakdown": {
            "skills": 0.85,
            "title": 0.9,
            "location": 1.0,
            "experience": 0.75,
            "industry": 0.7,
        },
        "matched_skills": ["Python", "SQL", "Python"],
        "missing_skills": ["AWS"],
        "rationale": "Strong title and skill alignment with one cloud gap.",
    }
    response.update(overrides)
    return response


class MatchingAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_structured_llm_output_and_grounded_resume_evidence(self) -> None:
        llm = FakeLLMService(match_response())
        agent = MatchingAgent(llm=llm, prompt_template=PROMPT)
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Private Candidate",
            email="private@example.com",
            summary="Builds reliable data platforms.",
            skills=("Python", "SQL"),
            years_experience=4,
            desired_titles=("Data Engineer",),
            desired_locations=("Denver, CO",),
        )
        knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python", "SQL"),
            years={"Python": 4, "SQL": 3},
            industries=("Retail",),
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

        result = await agent.score(candidate, job, knowledge)

        self.assertEqual(result.score, 0.82)
        self.assertEqual(result.breakdown.skills, 0.85)
        self.assertEqual(result.matched_skills, ("Python", "SQL"))
        self.assertEqual(result.missing_skills, ("AWS",))
        self.assertEqual(result.skill_years, {"Python": 4, "SQL": 3})
        self.assertEqual(len(llm.calls), 1)
        prompt, schema = llm.calls[0]
        self.assertIn("Builds reliable data platforms.", prompt)
        self.assertIn('"Python": 4.0', prompt)
        self.assertIn("Senior Data Engineer", prompt)
        self.assertNotIn(candidate.full_name, prompt)
        self.assertNotIn(candidate.email, prompt)
        self.assertEqual(schema["required"][0], "score")

    async def test_rejects_invalid_model_scores(self) -> None:
        llm = FakeLLMService(match_response(score=1.25))
        agent = MatchingAgent(llm=llm, prompt_template=PROMPT)
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            desired_titles=("Data Engineer",),
        )
        job = JobPosting(
            source="sample",
            external_id="job-1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1",
        )

        with self.assertRaisesRegex(InvalidMatchResponseError, "between 0 and 1"):
            await agent.score(candidate, job)

    def test_requires_every_prompt_evidence_placeholder(self) -> None:
        with self.assertRaisesRegex(ValueError, "resume_knowledge"):
            MatchingAgent(
                llm=FakeLLMService(match_response()),
                prompt_template="{candidate_profile}\n{job_posting}",
            )


if __name__ == "__main__":
    unittest.main()
