"""Score stored, unmatched jobs independently from source discovery."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agents import MatchingAgent, ParserAgent
from models import (
    CandidateProfile,
    JobPosting,
    MatchResult,
    ResumeKnowledgeBase,
    WorkflowRun,
    WorkflowStage,
    WorkflowStatus,
)
from repositories import JobProspectRepository
from services import NotificationService


GEMINI_MAX_REQUESTS_PER_MINUTE = 15


@dataclass(frozen=True, slots=True)
class JobMatchFailure:
    job: JobPosting
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class JobMatchingWorkflowResult:
    run: WorkflowRun
    jobs: tuple[JobPosting, ...]
    matches: tuple[MatchResult, ...]
    failures: tuple[JobMatchFailure, ...] = ()


class JobMatchingWorkflow:
    def __init__(
        self,
        *,
        repository: JobProspectRepository,
        parser_agent: ParserAgent,
        matching_agent: MatchingAgent,
        notifications: NotificationService,
        review_threshold: float = 0.7,
        max_requests_per_run: int = GEMINI_MAX_REQUESTS_PER_MINUTE,
    ) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between 0 and 1")
        if not 1 <= max_requests_per_run <= GEMINI_MAX_REQUESTS_PER_MINUTE:
            raise ValueError("max_requests_per_run must be between 1 and 15")
        self._repository = repository
        self._parser = parser_agent
        self._matching = matching_agent
        self._notifications = notifications
        self._review_threshold = review_threshold
        self._max_requests_per_run = max_requests_per_run

    async def run(
        self,
        candidate: CandidateProfile,
        resume_knowledge: ResumeKnowledgeBase | None = None,
        *,
        limit: int | None = None,
    ) -> JobMatchingWorkflowResult:
        requested_limit = self._max_requests_per_run if limit is None else limit
        if not 1 <= requested_limit <= GEMINI_MAX_REQUESTS_PER_MINUTE:
            raise ValueError("matching limit must be between 1 and 15")
        request_limit = min(requested_limit, self._max_requests_per_run)
        jobs = tuple(
            self._parser.parse(job)
            for job in self._repository.list_unmatched_jobs(limit=request_limit)
        )
        run = WorkflowRun("job_matching").record(
            WorkflowStage.SCORE,
            WorkflowStatus.RUNNING,
            f"Scoring up to {request_limit} unmatched jobs",
        )
        outcomes = await asyncio.gather(
            *(
                self._matching.score(candidate, job, resume_knowledge)
                for job in jobs
            ),
            return_exceptions=True,
        )
        matches: list[MatchResult] = []
        failures: list[JobMatchFailure] = []
        for job, outcome in zip(jobs, outcomes):
            if isinstance(outcome, asyncio.CancelledError):
                raise outcome
            if isinstance(outcome, BaseException):
                failures.append(
                    JobMatchFailure(
                        job=job,
                        error_type=type(outcome).__name__,
                        message=str(outcome),
                    )
                )
            else:
                matches.append(outcome)
        self._repository.update_matches(matches)
        run = run.record(
            WorkflowStage.SCORE,
            WorkflowStatus.COMPLETED,
            f"Scored {len(matches)} jobs; {len(failures)} failed",
        )
        review_count = sum(match.score >= self._review_threshold for match in matches)
        await self._notifications.notify(
            "job_review_required",
            f"{review_count} jobs meet the review threshold",
            metadata={"run_id": run.run_id},
        )
        run = run.record(
            WorkflowStage.REVIEW,
            WorkflowStatus.REVIEW_REQUIRED,
            f"{review_count} matches await human review",
            workflow_status=WorkflowStatus.REVIEW_REQUIRED,
        )
        matched_jobs = tuple(
            job
            for job, outcome in zip(jobs, outcomes)
            if not isinstance(outcome, BaseException)
        )
        return JobMatchingWorkflowResult(
            run=run,
            jobs=matched_jobs,
            matches=tuple(matches),
            failures=tuple(failures),
        )
