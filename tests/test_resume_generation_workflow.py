"""Single-job resume-generation workflow tests."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from dataclasses import replace
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
    ResumeDocumentFormat,
    ResumeKnowledgeBase,
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
    def __init__(self, *, target_title: str | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.target_title = target_title

    async def generate_resume(
        self,
        prompt: str,
        *,
        model: str,
    ) -> Mapping[str, Any]:
        self.calls.append((prompt, model))
        return {
            "target_title": self.target_title,
            "professional_summary": "Builds reliable data platforms.",
            "skills": ["Python", "SQL", "Data Warehousing"],
            "experience": [
                {
                    "company": "Example Corp",
                    "title": "Data Engineer",
                    "location": "Remote, US",
                    "start_date": "2022-01",
                    "end_date": "Present",
                    "responsibilities": ["Built a supported pipeline."],
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
            phone="(555) 123-4567",
            location="Denver, CO",
            linkedin_url="https://www.linkedin.com/in/example-candidate",
            github_url="https://github.com/example-candidate",
            website_url="https://example.dev",
            summary="Original Senior Software Engineer summary.",
            skills=("Python", "SQL"),
            additional_keywords=("Data Warehousing",),
            resume_path="/private/source-resume.pdf",
        )
        self.knowledge = ResumeKnowledgeBase.from_dict(
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
                        "responsibilities": ["Built a supported pipeline."],
                        "skills": ["Python"],
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
        *,
        target_title: str | None = None,
    ) -> tuple[ResumeGenerationWorkflow, StaticResumeGenerator]:
        generator = StaticResumeGenerator(target_title=target_title)
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
            self.assertNotIn("(555) 123-4567", prompt)
            self.assertNotIn("linkedin.com/in/example-candidate", prompt)
            self.assertNotIn("github.com/example-candidate", prompt)
            self.assertNotIn("example.dev", prompt)
            self.assertNotIn("Original Senior Software Engineer summary.", prompt)
            self.assertIn('"additional_keywords": [', prompt)
            self.assertIn('"Data Warehousing"', prompt)
            self.assertIn('"original_title": "Senior Data Engineer"', prompt)
            self.assertIn("Target Company", prompt)
            self.assertIn("Built a supported pipeline.", prompt)
            self.assertNotIn("/private/source-resume.pdf", prompt)
            self.assertNotIn("secret_source_payload", prompt)
            artifact_path = Path(result.artifact.path)
            self.assertTrue(artifact_path.exists())
            self.assertIn(self.job.job_id, artifact_path.name)
            self.assertEqual(artifact_path.suffix, ".html")
            self.assertEqual(result.prospect.resume_file_name, artifact_path.name)
            self.assertEqual(
                self.repository.get(self.job.job_id).resume_file_name,
                artifact_path.name,
            )
            html = artifact_path.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html)
            self.assertIn("<style>", html)
            self.assertIn("@media print", html)
            self.assertIn("Example Candidate", html)
            self.assertIn("candidate@example.com", html)
            self.assertIn("(555) 123-4567", html)
            self.assertIn("linkedin.com/in/example-candidate", html)
            self.assertIn("github.com/example-candidate", html)
            self.assertIn("example.dev", html)
            self.assertIn(
                '<span class="summary-title">Senior Data Engineer</span>'
                " — Builds reliable data platforms.",
                html,
            )
            self.assertIn("Professional Experience", html)
            self.assertIn("Remote, US", html)
            self.assertIn("January 2022 – Present", html)
            self.assertIn("Built a supported pipeline.", html)
            self.assertIn("Data Warehousing", html)
            self.assertIn("Improved platform reliability.", html)
            self.assertIn("Bachelor of Science in Computer Engineering", html)
            self.assertIn("Cloud Certification", html)
            self.assertIn("Issued January 2025", html)

    async def test_uses_job_description_title_before_job_prospect_title(self) -> None:
        self.repository.save_jobs((self.job,))
        prospect_title = "Principal Data Platform Engineer"
        self.repository.save(
            JobProspect(
                job_id=self.job.job_id,
                match=0.9,
                title=prospect_title,
                company=self.job.company,
                location="Remote, US",
                salary="Not provided",
                source=self.job.source,
                url=self.job.url,
                resume_generation_checked=True,
                resume_generation_candidate=True,
                resume_generation_model="gpt-5.4",
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            workflow, generator = self._workflow(directory)

            result = await workflow.run(
                job_id=self.job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )

            self.assertEqual(result.prospect.title, prospect_title)
            self.assertEqual(result.job.title, self.job.title)
            prompt, _ = generator.calls[0]
            self.assertIn(f'"original_title": "{self.job.title}"', prompt)
            self.assertNotIn(f'"original_title": "{prospect_title}"', prompt)
            html = Path(result.artifact.path).read_text(encoding="utf-8")
            self.assertIn(
                f'<span class="summary-title">{self.job.title}</span>',
                html,
            )
            self.assertNotIn(
                f'<span class="summary-title">{prospect_title}</span>',
                html,
            )

    async def test_uses_llm_title_declared_in_job_summary(self) -> None:
        summary_title = "Lead Data Platform Engineer"
        job = replace(
            self.job,
            description=(
                "Job Summary\n"
                f"We are seeking a {summary_title} to build reliable data products."
            ),
        )
        self.repository.save_jobs((job,))
        self.repository.update_matches(
            (
                MatchResult(
                    candidate_id=self.candidate.candidate_id,
                    job_id=job.job_id,
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
            workflow, _ = self._workflow(
                directory,
                target_title=summary_title,
            )

            result = await workflow.run(
                job_id=job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )

            html = Path(result.artifact.path).read_text(encoding="utf-8")
            self.assertIn(
                f'<span class="summary-title">{summary_title}</span>',
                html,
            )
            self.assertNotIn(
                f'<span class="summary-title">{job.title}</span>',
                html,
            )

    async def test_rejects_llm_title_not_declared_in_job_description(self) -> None:
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
            workflow, _ = self._workflow(
                directory,
                target_title="Invented Executive Title",
            )

            result = await workflow.run(
                job_id=self.job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )

            html = Path(result.artifact.path).read_text(encoding="utf-8")
            self.assertIn(
                f'<span class="summary-title">{self.job.title}</span>',
                html,
            )
            self.assertNotIn("Invented Executive Title", html)

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

    @unittest.skipUnless(
        importlib.util.find_spec("docx"),
        "python-docx is not installed",
    )
    async def test_generates_html_and_docx_from_one_model_response(self) -> None:
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
                document_format=ResumeDocumentFormat.BOTH,
            )

            self.assertEqual(len(generator.calls), 1)
            self.assertEqual(len(result.artifacts), 2)
            paths = tuple(Path(artifact.path) for artifact in result.artifacts)
            self.assertEqual({path.suffix for path in paths}, {".html", ".docx"})
            self.assertTrue(all(path.exists() for path in paths))
            docx_path = next(path for path in paths if path.suffix == ".docx")
            self.assertTrue(docx_path.read_bytes().startswith(b"PK"))
            self.assertEqual(result.prospect.resume_file_name, docx_path.name)
            self.assertEqual(
                self.repository.get(self.job.job_id).resume_file_name,
                docx_path.name,
            )

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
