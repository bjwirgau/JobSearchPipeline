"""Search → Normalize → Parse → Store orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from agents import ParserAgent, SearchAgent
from models import (
    JobPosting,
    SearchCriteria,
    SearchRunResult,
    WorkflowRun,
    WorkflowStage,
    WorkflowStatus,
)


@dataclass(frozen=True, slots=True)
class JobSearchWorkflowResult:
    run: WorkflowRun
    search: SearchRunResult
    jobs: tuple[JobPosting, ...]


class JobSearchWorkflow:
    def __init__(
        self,
        *,
        search_agent: SearchAgent,
        parser_agent: ParserAgent,
    ) -> None:
        self._search = search_agent
        self._parser = parser_agent

    def selected_source_names(
        self,
        criteria: SearchCriteria,
    ) -> tuple[str, ...]:
        return tuple(source.name for source in self._search.select_sources(criteria))

    async def run(
        self,
        criteria: SearchCriteria,
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
        self._search.store_jobs(parsed_jobs)
        run = run.record(
            WorkflowStage.PARSE,
            WorkflowStatus.COMPLETED,
            f"Parsed {len(parsed_jobs)} jobs",
            workflow_status=WorkflowStatus.COMPLETED,
        )
        return JobSearchWorkflowResult(run, search_result, parsed_jobs)
