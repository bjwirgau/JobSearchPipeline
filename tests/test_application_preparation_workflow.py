"""Review-only application preparation workflow tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents import ApplicationFormAnswerResult
from models import (
    ApplicationFieldKind,
    ApplicationFillResult,
    ApplicationFormField,
    CandidateProfile,
    JobPosting,
    JobProspect,
    ResumeKnowledgeBase,
)
from workflows import (
    ApplicationPreparationWorkflow,
    ApplicationResumeNotFoundError,
)


class StubRepository:
    def __init__(self, prospect: JobProspect, job: JobPosting) -> None:
        self.prospect = prospect
        self.job = job

    def get(self, job_id: str) -> JobProspect | None:
        return self.prospect if job_id == self.prospect.job_id else None

    def get_job_posting(self, job_id: str) -> JobPosting | None:
        return self.job if job_id == self.job.job_id else None


class StubFormAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[ApplicationFormField, ...]] = []

    async def answer(self, **arguments: object) -> ApplicationFormAnswerResult:
        fields = arguments["fields"]
        assert isinstance(fields, tuple)
        self.calls.append(fields)
        return ApplicationFormAnswerResult(
            answers={
                field.field_id: "Example"
                for field in fields
                if field.kind is not ApplicationFieldKind.FILE
            },
            unresolved_fields=(),
        )


class StubSession:
    def __init__(self, stages: tuple[tuple[ApplicationFormField, ...], ...]) -> None:
        self.stages = stages
        self.stage = 0
        self.closed = False
        self.advance_calls = 0
        self.disable_calls = 0

    @property
    def current_url(self) -> str:
        return "https://example.com/application"

    def inspect_fields(self) -> tuple[ApplicationFormField, ...]:
        return self.stages[self.stage]

    def fill_fields(
        self,
        answers: object,
        *,
        resume_path: Path,
    ) -> ApplicationFillResult:
        fields = self.stages[self.stage]
        return ApplicationFillResult(
            filled_field_ids=tuple(field.field_id for field in fields),
            resume_uploaded=any(
                field.kind is ApplicationFieldKind.FILE for field in fields
            ),
        )

    def open_application_form(self) -> bool:
        return False

    def advance(self) -> bool:
        self.advance_calls += 1
        if self.stage + 1 >= len(self.stages):
            return False
        self.stage += 1
        return True

    def disable_submission(self) -> int:
        self.disable_calls += 1
        return 1

    def close(self) -> None:
        self.closed = True


class StubBrowser:
    def __init__(self, session: StubSession) -> None:
        self.session = session
        self.urls: list[str] = []

    def open(self, url: str) -> StubSession:
        self.urls.append(url)
        return self.session


class ApplicationPreparationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.job = JobPosting(
            job_id="job-1",
            source="greenhouse",
            external_id="external-1",
            title="Software Engineer",
            company="Example",
            url="https://example.com/jobs/1",
        )
        self.prospect = JobProspect(
            job_id=self.job.job_id,
            match=0.9,
            title=self.job.title,
            company=self.job.company,
            location="Remote, US",
            salary="Not provided",
            source=self.job.source,
            url=self.job.url,
            resume_generation_checked=True,
            resume_generation_candidate=True,
            resume_generation_model="gpt-5.4",
            resume_file_name="candidate-job-1.docx",
        )
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
        )
        self.knowledge = ResumeKnowledgeBase(candidate_id="candidate-1")

    async def test_fills_multiple_steps_uploads_resume_and_leaves_session_open(self) -> None:
        stages = (
            (
                ApplicationFormField(
                    "name",
                    "Full Name",
                    ApplicationFieldKind.TEXT,
                    required=True,
                ),
                ApplicationFormField(
                    "resume",
                    "Resume / CV",
                    ApplicationFieldKind.FILE,
                    required=True,
                ),
            ),
            (
                ApplicationFormField(
                    "question",
                    "Why this role?",
                    ApplicationFieldKind.TEXTAREA,
                    required=True,
                ),
            ),
        )
        session = StubSession(stages)
        browser = StubBrowser(session)
        agent = StubFormAgent()
        with tempfile.TemporaryDirectory() as directory:
            resume = Path(directory) / self.prospect.resume_file_name
            resume.write_bytes(b"resume")
            workflow = ApplicationPreparationWorkflow(
                repository=StubRepository(self.prospect, self.job),  # type: ignore[arg-type]
                form_agent=agent,  # type: ignore[arg-type]
                browser=browser,
                generated_documents_dir=Path(directory),
            )

            result = await workflow.run(
                job_id=self.job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )

        self.assertTrue(result.complete)
        self.assertTrue(result.resume_uploaded)
        self.assertEqual(result.steps_completed, 2)
        self.assertGreaterEqual(result.submission_controls_disabled, 2)
        self.assertEqual(browser.urls, [self.job.url])
        self.assertFalse(session.closed)
        result.session.close()
        self.assertTrue(session.closed)

    async def test_rejects_a_prospect_without_a_generated_resume(self) -> None:
        prospect = JobProspect(
            job_id=self.job.job_id,
            match=0.9,
            title=self.job.title,
            company=self.job.company,
            location="Remote, US",
            salary="Not provided",
            source=self.job.source,
            url=self.job.url,
            resume_generation_checked=True,
            resume_generation_candidate=True,
            resume_generation_model="gpt-5.4",
        )
        session = StubSession(())
        workflow = ApplicationPreparationWorkflow(
            repository=StubRepository(prospect, self.job),  # type: ignore[arg-type]
            form_agent=StubFormAgent(),  # type: ignore[arg-type]
            browser=StubBrowser(session),
            generated_documents_dir=Path("/tmp/generated-documents"),
        )

        with self.assertRaisesRegex(
            ApplicationResumeNotFoundError,
            "no generated resume",
        ):
            await workflow.run(
                job_id=self.job.job_id,
                candidate=self.candidate,
                knowledge=self.knowledge,
            )
        self.assertFalse(session.closed)


if __name__ == "__main__":
    unittest.main()
