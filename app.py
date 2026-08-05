"""Application composition root and CLI for the Phase 3 job-agent pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from agents import (
    ApplyAgent,
    CoverLetterAgent,
    MatchingAgent,
    ParserAgent,
    SearchAgent,
    SearchQueryBuilder,
    TailoringAgent,
    ValidationAgent,
)
from config import Settings
from database import Database, MySQLConfig, initialize_schema
from models import (
    CandidateProfile,
    JobPosting,
    MatchResult,
    ResumeKnowledgeBase,
    SearchCriteria,
)
from repositories import (
    ApplicationRepository,
    CandidateRepository,
    JobRepository,
    ResumeKnowledgeRepository,
)
from services import (
    DocumentService,
    LoggingNotificationService,
    ResumeKnowledgeError,
    ResumeKnowledgeService,
    build_job_sources,
)
from services.job_sources import LinkedInJobSource
from utils.logging import configure_logging
from workflows import ApplicationWorkflow, JobSearchWorkflow


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    settings: Settings
    database: Database
    candidates: CandidateRepository
    jobs: JobRepository
    applications: ApplicationRepository
    resume_knowledge: ResumeKnowledgeRepository
    resume_knowledge_service: ResumeKnowledgeService
    job_search_workflow: JobSearchWorkflow
    application_workflow: ApplicationWorkflow


def build_container(settings: Settings | None = None) -> ApplicationContainer:
    settings = settings or Settings.from_env()
    settings.prepare_directories()
    database = Database(
        MySQLConfig(
            host=settings.mysql_host,
            port=settings.mysql_port,
            database=settings.mysql_database,
            user=settings.mysql_user,
            password=settings.mysql_password,
            connection_timeout=settings.mysql_connect_timeout,
        )
    )
    initialize_schema(database)

    candidates = CandidateRepository(database)
    jobs = JobRepository(database)
    applications = ApplicationRepository(database)
    resume_knowledge = ResumeKnowledgeRepository(database)
    resume_knowledge_service = ResumeKnowledgeService(settings.candidate_profile_path)
    documents = DocumentService(settings.generated_documents_dir)
    notifications = LoggingNotificationService()

    try:
        skill_vocabulary = resume_knowledge_service.load().all_skills
    except ResumeKnowledgeError as error:
        logging.getLogger(__name__).warning(
            "Resume knowledge unavailable for job normalization: %s",
            error,
        )
        skill_vocabulary = ()
    job_sources = build_job_sources(
        settings,
        skill_vocabulary=skill_vocabulary,
    )

    search_agent = SearchAgent(
        sources=job_sources,
        repository=jobs,
        enabled=settings.search_enabled,
    )
    parser_agent = ParserAgent()
    matching_agent = MatchingAgent()
    tailoring_agent = TailoringAgent(documents)
    cover_letter_agent = CoverLetterAgent(documents)
    validation_agent = ValidationAgent()
    apply_agent = ApplyAgent(
        repository=applications,
        enabled=settings.application_submission_enabled,
    )

    return ApplicationContainer(
        settings=settings,
        database=database,
        candidates=candidates,
        jobs=jobs,
        applications=applications,
        resume_knowledge=resume_knowledge,
        resume_knowledge_service=resume_knowledge_service,
        job_search_workflow=JobSearchWorkflow(
            search_agent=search_agent,
            parser_agent=parser_agent,
            matching_agent=matching_agent,
            notifications=notifications,
        ),
        application_workflow=ApplicationWorkflow(
            repository=applications,
            tailoring_agent=tailoring_agent,
            cover_letter_agent=cover_letter_agent,
            validation_agent=validation_agent,
            apply_agent=apply_agent,
            notifications=notifications,
        ),
    )


def _arguments(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review-first job search pipeline")
    parser.add_argument("--search", action="store_true", help="run configured job sources")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print Apify Actor inputs without sending requests",
    )
    parser.add_argument("--title", action="append", default=[], help="desired job title")
    parser.add_argument("--skill", action="append", default=[], help="search skill")
    parser.add_argument(
        "--requirement",
        action="append",
        default=[],
        help="keyword that must appear in the job",
    )
    parser.add_argument("--location", action="append", default=[], help="desired location")
    parser.add_argument(
        "--radius",
        type=int,
        help="location search radius in miles",
    )
    parser.add_argument("--source", action="append", default=[], help="configured source name")
    parser.add_argument("--remote", action="store_true", help="require explicitly remote jobs")
    parser.add_argument(
        "--remote-country",
        default=settings.remote_country if settings else None,
        help="two-letter country code used to filter remote-job eligibility",
    )
    parser.add_argument(
        "--employment-type",
        action="append",
        default=[],
        help="accepted type such as full-time, part-time, or contract",
    )
    parser.add_argument("--minimum-salary", type=int, help="minimum annual salary")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="keyword that must not appear in the job",
    )
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="oldest accepted posting in days",
    )
    parser.add_argument("--limit", type=int, default=25, help="results per source query")
    arguments = parser.parse_args(argv)
    if arguments.dry_run and not arguments.search:
        parser.error("--dry-run requires --search")
    unsupported_dry_run_sources = tuple(
        source
        for source in arguments.source
        if source.strip().casefold() != "linkedin"
    )
    if arguments.dry_run and unsupported_dry_run_sources:
        parser.error("--dry-run supports only the linkedin source")
    return arguments


def _load_candidate(path: Path) -> CandidateProfile:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("candidate profile must contain a JSON object")
    return CandidateProfile.from_dict(value)


def _search_criteria(
    arguments: argparse.Namespace,
    candidate: CandidateProfile,
    knowledge: ResumeKnowledgeBase,
) -> SearchCriteria:
    return SearchCriteria(
        job_titles=tuple(arguments.title) or candidate.desired_titles,
        skills=tuple(arguments.skill) or knowledge.all_skills,
        required_keywords=tuple(arguments.requirement),
        locations=tuple(arguments.location) or candidate.desired_locations,
        location_radius_miles=arguments.radius,
        remote_only=arguments.remote or candidate.remote_preference == "remote",
        remote_country=arguments.remote_country,
        employment_types=tuple(arguments.employment_type),
        minimum_salary=arguments.minimum_salary,
        excluded_keywords=tuple(arguments.exclude),
        max_age_days=arguments.max_age_days,
        source_names=tuple(arguments.source),
        results_per_query=arguments.limit,
    )


def _format_job_grid(
    ranked: Sequence[tuple[JobPosting, MatchResult]],
) -> str:
    columns = (
        ("#", 3),
        ("Match", 5),
        ("Title", 28),
        ("Company", 22),
        ("Location", 22),
        ("Salary", 22),
        ("Source", 12),
        ("URL", 44),
    )
    rows = [
        (
            str(index),
            f"{match.score:.0%}",
            job.title,
            job.company,
            job.location or "Not provided",
            _format_salary(job),
            job.source,
            job.url,
        )
        for index, (job, match) in enumerate(ranked, 1)
    ]
    widths = tuple(
        min(
            maximum,
            max((len(header), *(len(str(row[index])) for row in rows))),
        )
        for index, (header, maximum) in enumerate(columns)
    )
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def render_row(values: Sequence[str]) -> list[str]:
        wrapped = [
            textwrap.wrap(
                " ".join(str(value).split()),
                width=width,
                break_long_words=True,
                break_on_hyphens=False,
            )
            or [""]
            for value, width in zip(values, widths)
        ]
        return [
            "|"
            + "|".join(
                f" {parts[line] if line < len(parts) else '':<{width}} "
                for parts, width in zip(wrapped, widths)
            )
            + "|"
            for line in range(max(len(parts) for parts in wrapped))
        ]

    lines = [border, *render_row(tuple(header for header, _ in columns)), border]
    for row in rows:
        lines.extend(render_row(row))
        lines.append(border)
    return "\n".join(lines)


def _format_salary(job: JobPosting) -> str:
    currency = job.salary_currency or ""
    if job.salary_min is None and job.salary_max is None:
        return "Not disclosed"
    if job.salary_min is not None and job.salary_max is not None:
        amount = f"{job.salary_min:,}-{job.salary_max:,}"
    elif job.salary_min is not None:
        amount = f"{job.salary_min:,}+"
    else:
        amount = f"Up to {job.salary_max:,}"
    return " ".join(value for value in (currency, amount) if value)


def _format_searched_sources(source_names: Sequence[str]) -> str:
    names = ", ".join(source_names) if source_names else "none"
    return f"Searching sources ({len(source_names)}): {names}"


def _format_apify_dry_run(criteria: SearchCriteria, *, actor_id: str) -> str:
    queries = SearchQueryBuilder().build(criteria)
    lines = [
        "Apify dry run: no requests sent.",
        f"Actor: {actor_id}",
        f"Queries: {len(queries)}",
    ]
    for index, query in enumerate(queries, 1):
        payload = LinkedInJobSource.build_actor_input(
            query,
            criteria.results_per_query,
        )
        lines.extend(
            (
                f"Query {index}/{len(queries)}:",
                json.dumps(payload, indent=2, ensure_ascii=False),
            )
        )
    return "\n".join(lines)


def _run_apify_dry_run(settings: Settings, arguments: argparse.Namespace) -> int:
    candidate = _load_candidate(settings.candidate_profile_path)
    knowledge = ResumeKnowledgeService(settings.candidate_profile_path).load()
    criteria = _search_criteria(arguments, candidate, knowledge)
    print(
        _format_apify_dry_run(
            criteria,
            actor_id=settings.apify_linkedin_actor_id,
        )
    )
    return 0


async def _run_search(
    container: ApplicationContainer,
    arguments: argparse.Namespace,
) -> int:
    candidate = _load_candidate(container.settings.candidate_profile_path)
    knowledge = container.resume_knowledge_service.load()
    criteria = _search_criteria(arguments, candidate, knowledge)
    logging.getLogger(__name__).info(
        "Search criteria remote country: %s",
        criteria.remote_country,
    )
    selected_sources = container.job_search_workflow.selected_source_names(criteria)
    print(_format_searched_sources(selected_sources), flush=True)
    result = await container.job_search_workflow.run(candidate, criteria, knowledge)
    ranked = sorted(
        zip(result.jobs, result.matches),
        key=lambda item: item[1].score,
        reverse=True,
    )
    print(
        f"Found {result.search.fetched_count} jobs; "
        f"stored {result.search.stored_count}; "
        f"{len(result.search.failures)} source requests failed."
    )
    print(_format_job_grid(ranked))
    for failure in result.search.failures:
        logging.getLogger(__name__).warning(
            "source=%s query=%s error=%s: %s",
            failure.source,
            failure.query.text,
            failure.error_type,
            failure.message,
        )
    return 0 if ranked or not result.search.failures else 1


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings.from_env()
    arguments = _arguments(argv, settings=settings)
    configure_logging(settings.log_level)
    if arguments.search and arguments.dry_run:
        return _run_apify_dry_run(settings, arguments)
    container = build_container(settings)
    logging.getLogger(__name__).info(
        "Job Agent Phase 3 initialized "
        "(search=%s, submission=%s, database=%s@%s:%s/%s)",
        settings.search_enabled,
        settings.application_submission_enabled,
        settings.mysql_user,
        settings.mysql_host,
        settings.mysql_port,
        settings.mysql_database,
    )
    if arguments.search:
        return asyncio.run(_run_search(container, arguments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
