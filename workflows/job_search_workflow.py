"""Search → Normalize → Parse → Score → Review orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agents import MatchingAgent, ParserAgent, SearchAgent
from models import (
    CandidateProfile,
    JobPosting,
    MatchResult,
    ResumeKnowledgeBase,
    SearchCriteria,
    SearchRunResult,
    WorkflowRun,
    WorkflowStage,
    WorkflowStatus,
)
from services import NotificationService


@dataclass(frozen=True, slots=True)
class JobSearchWorkflowResult:
    run: WorkflowRun
    search: SearchRunResult
    jobs: tuple[JobPosting, ...]
    matches: tuple[MatchResult, ...]


class JobSearchWorkflow:
    def __init__(
        self,
        *,
        search_agent: SearchAgent,
        parser_agent: ParserAgent,
        matching_agent: MatchingAgent,
        notifications: NotificationService,
        review_threshold: float = 0.7,
    ) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between 0 and 1")
        self._search = search_agent
        self._parser = parser_agent
        self._matching = matching_agent
        self._notifications = notifications
        self._review_threshold = review_threshold

    def selected_source_names(
        self,
        criteria: SearchCriteria,
    ) -> tuple[str, ...]:
        return tuple(source.name for source in self._search.select_sources(criteria))

    async def run(
        self,
        candidate: CandidateProfile,
        criteria: SearchCriteria,
        resume_knowledge: ResumeKnowledgeBase | None = None,
        *,
        score_existing: bool = True,
    ) -> JobSearchWorkflowResult:
        run = WorkflowRun("job_search").record(
            WorkflowStage.SEARCH,
            WorkflowStatus.RUNNING,
            "Search started",
        )
        search_result = await self._search.search(criteria)
        run = run.record(
            WorkflowStage.SEARCH,
            WorkflowStatus.COMPLETED,
            f"Found {search_result.deduplicated_count} distinct jobs",
        )
        run = run.record(
            WorkflowStage.NORMALIZE,
            WorkflowStatus.COMPLETED,
            "Source adapters returned normalized job models",
        )

        parsed_jobs = tuple(self._parser.parse(job) for job in search_result.jobs)
        run = run.record(
            WorkflowStage.PARSE,
            WorkflowStatus.COMPLETED,
            f"Parsed {len(parsed_jobs)} jobs",
        )
        jobs_to_score = (
            parsed_jobs
            if score_existing
            else self._search.unmatched_jobs(parsed_jobs)
        )
        matches = tuple(
            await asyncio.gather(
                *(
                    self._matching.score(candidate, job, resume_knowledge)
                    for job in jobs_to_score
                )
            )
        )
        self._search.store_matches(matches)
        run = run.record(
            WorkflowStage.SCORE,
            WorkflowStatus.COMPLETED,
            f"Scored {len(matches)} jobs",
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
        return JobSearchWorkflowResult(run, search_result, jobs_to_score, matches)
