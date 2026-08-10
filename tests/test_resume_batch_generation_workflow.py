"""Batch resume-generation queue tests."""

from __future__ import annotations

import unittest

from models import (
    CandidateProfile,
    DocumentArtifact,
    JobPosting,
    JobProspect,
    ResumeDocumentFormat,
    ResumeKnowledgeBase,
)
from workflows import (
    ResumeBatchGenerationWorkflow,
    ResumeGenerationWorkflowResult,
)


def _prospect(job_id: str, match: float) -> JobProspect:
    return JobProspect(
        job_id=job_id,
        match=match,
        title="Senior Engineer",
        company="Example Corp",
        location="Remote, US",
        salary="Not provided",
        source="greenhouse",
        url=f"https://example.com/jobs/{job_id}",
        resume_generation_checked=True,
        resume_generation_candidate=True,
        resume_generation_model="gpt-5.4",
    )


class StubRepository:
    def __init__(self, prospects: tuple[JobProspect, ...]) -> None:
        self.prospects = prospects
        self.limits: list[int] = []
        self.attempts: list[str] = []

    def list_pending_resume_generation_candidates(
        self,
        *,
        limit: int,
    ) -> tuple[JobProspect, ...]:
        self.limits.append(limit)
        return self.prospects[:limit]

    def record_resume_generation_attempt(self, job_id: str) -> None:
        self.attempts.append(job_id)


class StubResumeGenerationWorkflow:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[tuple[str, ResumeDocumentFormat]] = []

    async def run(self, **arguments: object) -> ResumeGenerationWorkflowResult:
        job_id = str(arguments["job_id"])
        document_format = arguments["document_format"]
        assert isinstance(document_format, ResumeDocumentFormat)
        self.calls.append((job_id, document_format))
        if job_id in self.failures:
            raise RuntimeError("generation unavailable")
        prospect = _prospect(job_id, 0.9)
        prospect = JobProspect.from_row(
            {**prospect.to_dict(), "resume_file_name": f"{job_id}.docx"}
        )
        job = JobPosting(
            job_id=job_id,
            source="greenhouse",
            external_id=job_id,
            title=prospect.title,
            company=prospect.company,
            url=prospect.url,
        )
        return ResumeGenerationWorkflowResult(
            prospect=prospect,
            job=job,
            artifacts=(
                DocumentArtifact(
                    kind="resume",
                    path=f"/tmp/{job_id}.docx",
                    content_hash="hash",
                ),
            ),
            model="gpt-5.4",
        )


class ResumeBatchGenerationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_processes_pending_jobs_and_continues_after_a_failure(self) -> None:
        prospects = (_prospect("job-1", 0.95), _prospect("job-2", 0.9))
        repository = StubRepository(prospects)
        generator = StubResumeGenerationWorkflow({"job-1"})
        workflow = ResumeBatchGenerationWorkflow(
            repository=repository,  # type: ignore[arg-type]
            resume_generation=generator,  # type: ignore[arg-type]
        )

        with self.assertLogs(
            "workflows.resume_batch_generation_workflow",
            level="ERROR",
        ):
            result = await workflow.run(
                candidate=CandidateProfile(
                    candidate_id="candidate-1",
                    full_name="Example Candidate",
                    email="candidate@example.com",
                ),
                knowledge=ResumeKnowledgeBase(candidate_id="candidate-1"),
                limit=2,
                document_format="docx",
            )

        self.assertEqual(repository.limits, [2])
        self.assertEqual(repository.attempts, ["job-1", "job-2"])
        self.assertEqual(
            generator.calls,
            [
                ("job-1", ResumeDocumentFormat.DOCX),
                ("job-2", ResumeDocumentFormat.DOCX),
            ],
        )
        self.assertEqual([item.job.job_id for item in result.generated], ["job-2"])
        self.assertEqual([item.prospect.job_id for item in result.failures], ["job-1"])
        self.assertEqual(result.failures[0].error_type, "RuntimeError")

    async def test_validates_batch_limit_before_querying(self) -> None:
        repository = StubRepository(())
        workflow = ResumeBatchGenerationWorkflow(
            repository=repository,  # type: ignore[arg-type]
            resume_generation=StubResumeGenerationWorkflow(),  # type: ignore[arg-type]
        )

        with self.assertRaisesRegex(ValueError, "between 1 and 100"):
            await workflow.run(
                candidate=CandidateProfile(
                    candidate_id="candidate-1",
                    full_name="Example Candidate",
                    email="candidate@example.com",
                ),
                knowledge=ResumeKnowledgeBase(candidate_id="candidate-1"),
                limit=101,
            )
        self.assertEqual(repository.limits, [])


if __name__ == "__main__":
    unittest.main()
