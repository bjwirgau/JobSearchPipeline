"""Review → Tailor → Apply → Track orchestration with an approval gate."""

from __future__ import annotations

from dataclasses import dataclass, replace

from agents import ApplyAgent, CoverLetterAgent, TailoringAgent, ValidationAgent
from models import (
    Application,
    ApplicationStatus,
    CandidateProfile,
    DocumentArtifact,
    JobPosting,
    MatchResult,
    WorkflowRun,
    WorkflowStage,
    WorkflowStatus,
)
from repositories import ApplicationRepository
from services import NotificationService
from utils.dates import utc_now


@dataclass(frozen=True, slots=True)
class ApplicationWorkflowResult:
    run: WorkflowRun
    application: Application
    artifacts: tuple[DocumentArtifact, ...] = ()


class ApplicationWorkflow:
    def __init__(
        self,
        *,
        repository: ApplicationRepository,
        tailoring_agent: TailoringAgent,
        cover_letter_agent: CoverLetterAgent,
        validation_agent: ValidationAgent,
        apply_agent: ApplyAgent,
        notifications: NotificationService,
    ) -> None:
        self._repository = repository
        self._tailoring = tailoring_agent
        self._cover_letter = cover_letter_agent
        self._validation = validation_agent
        self._apply = apply_agent
        self._notifications = notifications

    async def request_review(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
    ) -> ApplicationWorkflowResult:
        application = Application(
            candidate_id=candidate.candidate_id,
            job_id=job.job_id,
            status=ApplicationStatus.REVIEW_REQUIRED,
        )
        self._repository.save(application)
        await self._notifications.notify(
            "application_review_required",
            f"Review {job.title} at {job.company}",
            metadata={"application_id": application.application_id},
        )
        run = WorkflowRun("application").record(
            WorkflowStage.REVIEW,
            WorkflowStatus.REVIEW_REQUIRED,
            "Application awaits explicit user approval",
            workflow_status=WorkflowStatus.REVIEW_REQUIRED,
        )
        return ApplicationWorkflowResult(run, application)

    def approve(self, application: Application) -> Application:
        if application.status is not ApplicationStatus.REVIEW_REQUIRED:
            raise ValueError("only applications awaiting review can be approved")
        approved = replace(
            application,
            status=ApplicationStatus.APPROVED,
            updated_at=utc_now(),
        )
        self._repository.save(approved)
        return approved

    def tailor(
        self,
        *,
        candidate: CandidateProfile,
        job: JobPosting,
        match: MatchResult,
        application: Application,
    ) -> ApplicationWorkflowResult:
        if application.status is not ApplicationStatus.APPROVED:
            raise ValueError("application must be approved before tailoring")
        resume = self._tailoring.create_brief(candidate, job, match)
        cover_letter = self._cover_letter.draft(candidate, job, match)
        ready = replace(
            application,
            status=ApplicationStatus.READY,
            resume_path=resume.path,
            cover_letter_path=cover_letter.path,
            updated_at=utc_now(),
        )
        self._repository.save(ready)
        run = WorkflowRun("application").record(
            WorkflowStage.TAILOR,
            WorkflowStatus.COMPLETED,
            "Draft documents are ready for final review",
            workflow_status=WorkflowStatus.REVIEW_REQUIRED,
        )
        return ApplicationWorkflowResult(run, ready, (resume, cover_letter))

    async def submit(
        self,
        *,
        candidate: CandidateProfile,
        job: JobPosting,
        application: Application,
        match: MatchResult,
        user_approved: bool,
    ) -> ApplicationWorkflowResult:
        validation = self._validation.validate(
            candidate=candidate,
            job=job,
            application=application,
            match=match,
            user_approved=user_approved,
        )
        submitted = await self._apply.submit(application, validation)
        run = WorkflowRun("application").record(
            WorkflowStage.APPLY,
            WorkflowStatus.COMPLETED,
            "Application submitted",
        ).record(
            WorkflowStage.TRACK,
            WorkflowStatus.COMPLETED,
            "Submission stored for tracking",
            workflow_status=WorkflowStatus.COMPLETED,
        )
        return ApplicationWorkflowResult(run, submitted)
