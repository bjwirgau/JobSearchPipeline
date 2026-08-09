"""Score stored, unmatched jobs independently from source discovery."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from agents import MatchingAgent, ParserAgent
from models import (
    CandidateProfile,
    DEFAULT_RESUME_CANDIDATE_THRESHOLD,
    DEFAULT_RESUME_GENERATION_MODEL,
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
LOGGER = logging.getLogger(__name__)


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
    resume_candidates: tuple[JobPosting, ...] = ()
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
        resume_candidate_threshold: float = DEFAULT_RESUME_CANDIDATE_THRESHOLD,
        resume_generation_model: str = DEFAULT_RESUME_GENERATION_MODEL,
        max_requests_per_run: int = GEMINI_MAX_REQUESTS_PER_MINUTE,
    ) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between 0 and 1")
        if not 0 <= resume_candidate_threshold < 1:
            raise ValueError(
                "resume_candidate_threshold must be at least 0 and less than 1"
            )
        if not resume_generation_model.strip():
            raise ValueError("resume_generation_model must not be empty")
        if not 1 <= max_requests_per_run <= GEMINI_MAX_REQUESTS_PER_MINUTE:
            raise ValueError("max_requests_per_run must be between 1 and 15")
        self._repository = repository
        self._parser = parser_agent
        self._matching = matching_agent
        self._notifications = notifications
        self._review_threshold = review_threshold
        self._resume_candidate_threshold = resume_candidate_threshold
        self._resume_generation_model = resume_generation_model.strip()
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
            for job in self._repository.list_unchecked_resume_generation_jobs(
                limit=request_limit
            )
        )
        run = WorkflowRun("job_matching").record(
            WorkflowStage.SCORE,
            WorkflowStatus.RUNNING,
            f"Grading up to {request_limit} unchecked jobs",
        )
        for job in jobs:
            LOGGER.info(
                "Checking resume generation eligibility: "
                "job_id=%s title=%s company=%s threshold=%.2f%%",
                job.job_id,
                job.title,
                job.company,
                self._resume_candidate_threshold * 100,
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
                LOGGER.info(
                    "Resume generation eligibility checked: "
                    "job_id=%s title=%s company=%s score=%.2f%% qualified=%s",
                    job.job_id,
                    job.title,
                    job.company,
                    outcome.score * 100,
                    outcome.score > self._resume_candidate_threshold,
                )
        self._repository.update_matches(
            matches,
            resume_candidate_threshold=self._resume_candidate_threshold,
            resume_generation_model=self._resume_generation_model,
        )
        run = run.record(
            WorkflowStage.SCORE,
            WorkflowStatus.COMPLETED,
            f"Scored {len(matches)} jobs; {len(failures)} failed",
        )
        review_count = sum(match.score >= self._review_threshold for match in matches)
        resume_candidate_ids = {
            match.job_id
            for match in matches
            if match.score > self._resume_candidate_threshold
        }
        resume_candidates = tuple(
            job for job in jobs if job.job_id in resume_candidate_ids
        )
        await self._notifications.notify(
            "job_review_required",
            f"{review_count} jobs meet the review threshold",
            metadata={"run_id": run.run_id},
        )
        if resume_candidates:
            await self._notifications.notify(
                "resume_generation_candidate",
                f"{len(resume_candidates)} jobs qualify for resume generation",
                metadata={
                    "run_id": run.run_id,
                    "model": self._resume_generation_model,
                    "threshold": str(self._resume_candidate_threshold),
                },
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
            resume_candidates=resume_candidates,
            failures=tuple(failures),
        )
