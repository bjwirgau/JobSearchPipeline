"""Application composition root and CLI for the Phase 3 job-agent pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from agents import (
    ApplyAgent,
    CoverLetterAgent,
    MatchingAgent,
    ParserAgent,
    SearchAgent,
    TailoringAgent,
    ValidationAgent,
)
from config import Settings
from database import Database, initialize_schema
from models import CandidateProfile, ResumeKnowledgeBase, SearchCriteria
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
    database = Database(settings.database_path)
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
    return parser.parse_args(argv)


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
    for job, match in ranked:
        salary = ""
        if job.salary_min is not None or job.salary_max is not None:
            salary = (
                f" | salary={job.salary_currency or ''} "
                f"{job.salary_min or '?'}-{job.salary_max or '?'}"
            )
        print(
            f"{match.score:.0%} | {job.title} | {job.company} | "
            f"{job.location or 'Location unavailable'}{salary}\n"
            f"  {job.url}"
        )
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
    container = build_container(settings)
    logging.getLogger(__name__).info(
        "Job Agent Phase 3 initialized (search=%s, submission=%s, database=%s)",
        settings.search_enabled,
        settings.application_submission_enabled,
        settings.database_path,
    )
    if arguments.search:
        return asyncio.run(_run_search(container, arguments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
