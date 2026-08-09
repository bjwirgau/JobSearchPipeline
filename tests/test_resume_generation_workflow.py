"""Single-job resume-generation workflow tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from agents import ResumeGenerationAgent
from database import Database, MySQLConfig, initialize_schema
from models import (
    CandidateProfile,
    JobPosting,
    JobProspect,
    MatchBreakdown,
    MatchResult,
    ResumeKnowledgeBase,
    ResumeRole,
)
from repositories import JobProspectRepository
from services import DocumentService
from tests.mysql_fakes import FakeMySQLServer
from workflows import (
    ResumeGenerationJobDataError,
    ResumeGenerationJobNotFoundError,
    ResumeGenerationNotEligibleError,
    ResumeGenerationWorkflow,
)


PROMPT = """\
CANDIDATE\n{candidate_profile}\nKNOWLEDGE\n{resume_knowledge}\nJOB\n{job_posting}
"""


class StaticResumeGenerator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def generate_resume(
        self,
        prompt: str,
        *,
        model: str,
    ) -> Mapping[str, Any]:
        self.calls.append((prompt, model))
        return {
            "professional_summary": "Builds reliable data platforms.",
            "skills": ["Python", "SQL"],
            "experience": [
                {
                    "company": "Example Corp",
                    "title": "Data Engineer",
                    "start_date": None,
                    "end_date": None,
                    "achievements": ["Built a supported pipeline."],
                }
            ],
            "career_highlights": [],
            "education": [],
            "certifications": [],
        }


class ResumeGenerationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = JobProspectRepository(database)
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            location="Denver, CO",
            summary="Builds reliable data platforms.",
            skills=("Python", "SQL"),
            resume_path="/private/source-resume.pdf",
        )
        self.knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python", "SQL"),
            roles=(
                ResumeRole(
                    company="Example Corp",
                    title="Data Engineer",
                    achievements=("Built a supported pipeline.",),
                    skills=("Python",),
                ),
            ),
        )
        self.job = JobPosting(
            source="greenhouse",
            external_id="job-1",
            title="Senior Data Engineer",
            company="Target Company",
            url="https://example.com/jobs/1",
            description="Build data products.",
            skills=("Python", "SQL"),
            raw={"secret_source_payload": "must not be sent"},
        )

    def _workflow(
        self,
        directory: str,
    ) -> tuple[ResumeGenerationWorkflow, StaticResumeGenerator]:
        generator = StaticResumeGenerator()
        workflow = ResumeGenerationWorkflow(
            repository=self.repository,
            agent=ResumeGenerationAgent(
                generator=generator,
                documents=DocumentService(directory),
                prompt_template=PROMPT,
            ),
        )
        return workflow, generator

    async def test_generates_only_the_requested_marked_job(self) -> None:
        self.repository.save_jobs((self.job,))
        self.repository.update_matches(
            (
                MatchResult(
                    candidate_id=self.candidate.candidate_id,
                    job_id=self.job.job_id,
                    score=0.9,
                    breakdown=MatchBreakdown(
                        skills=0.9,
                        title=0.9,
                        location=0.9,
                        experience=0.9,
                    ),
                ),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            workflow, generator = self._workflow(directory)

            result = await workflow.run(
                job_id=self.job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )

            self.assertEqual(result.job, self.job)
            self.assertEqual(result.model, "gpt-5.4")
            self.assertEqual(len(generator.calls), 1)
            prompt, model = generator.calls[0]
            self.assertEqual(model, "gpt-5.4")
            self.assertNotIn("Example Candidate", prompt)
            self.assertNotIn("candidate@example.com", prompt)
            self.assertIn("Target Company", prompt)
            self.assertIn("Built a supported pipeline.", prompt)
            self.assertNotIn("/private/source-resume.pdf", prompt)
            self.assertNotIn("secret_source_payload", prompt)
            artifact_path = Path(result.artifact.path)
            self.assertTrue(artifact_path.exists())
            self.assertIn(self.job.job_id, artifact_path.name)
            self.assertEqual(artifact_path.suffix, ".html")
            html = artifact_path.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html)
            self.assertIn("<style>", html)
            self.assertIn("@media print", html)
            self.assertIn("Example Candidate", html)
            self.assertIn("candidate@example.com", html)
            self.assertIn("Professional Experience", html)
            self.assertIn("Built a supported pipeline.", html)

    async def test_rejects_job_that_is_not_marked_for_generation(self) -> None:
        self.repository.save_jobs((self.job,))
        with tempfile.TemporaryDirectory() as directory:
            workflow, generator = self._workflow(directory)

            with self.assertRaisesRegex(
                ResumeGenerationNotEligibleError,
                "not marked",
            ):
                await workflow.run(
                    job_id=self.job.job_id,
                    candidate=self.candidate,
                    knowledge=self.knowledge,
                )

        self.assertEqual(generator.calls, [])

    async def test_reports_unknown_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workflow, _ = self._workflow(directory)

            with self.assertRaisesRegex(
                ResumeGenerationJobNotFoundError,
                "not found",
            ):
                await workflow.run(
                    job_id="unknown-job",
                    candidate=self.candidate,
                    knowledge=self.knowledge,
                )

    async def test_reports_marked_job_without_normalized_data(self) -> None:
        self.repository.save(
            JobProspect(
                job_id="legacy-job",
                match=0.9,
                title="Senior Data Engineer",
                company="Target Company",
                location="Remote",
                salary="Not provided",
                source="legacy",
                url="https://example.com/jobs/legacy",
                resume_generation_checked=True,
                resume_generation_candidate=True,
                resume_generation_model="gpt-5.4",
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            workflow, _ = self._workflow(directory)

            with self.assertRaisesRegex(
                ResumeGenerationJobDataError,
                "no normalized job data",
            ):
                await workflow.run(
                    job_id="legacy-job",
                    candidate=self.candidate,
                    knowledge=self.knowledge,
                )


if __name__ == "__main__":
    unittest.main()
