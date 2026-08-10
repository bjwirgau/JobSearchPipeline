"""Composition root and CLI for the Phase 3 job-agent pipeline."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import textwrap
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Sequence

from agents import (
    CompanyCrawlerDisabledError,
    GreenhouseCompanyCrawler,
    MatchingAgent,
    ParserAgent,
    ResumeGenerationAgent,
    SearchAgent,
    SearchQueryBuilder,
)
from config import Settings
from database import Database, MySQLConfig, initialize_schema
from models import (
    CandidateProfile,
    CompanyProspect,
    JobPosting,
    MatchResult,
    ResumeKnowledgeBase,
    SearchCriteria,
)
from repositories import (
    CompanyProspectRepository,
    CrawlDiscoveryCursorRepository,
    CrawlPageRepository,
    JobProspectRepository,
    ResumeKnowledgeRepository,
)
from services import (
    CompanyDiscoveryError,
    DisabledResumeGenerator,
    DisabledLLMService,
    DocumentService,
    GeminiConfig,
    GeminiLLMService,
    GreenhouseCdxDiscovery,
    GreenhousePublicBoardLookup,
    LoggingNotificationService,
    MissingDocxDependencyError,
    MissingOpenAIDependencyError,
    OpenAIResumeConfig,
    OpenAIResumeGenerator,
    RequestsHttpClient,
    ResumeGenerationNotConfiguredError,
    ResumeGenerationResponseError,
    ResumeKnowledgeError,
    ResumeKnowledgeService,
    ThrottledHttpClient,
    build_job_sources,
)
from services.http_service import HttpRequestError
from services.job_sources import GreenhouseBoard, LinkedInJobSource
from utils.logging import configure_logging
from workflows import (
    JobMatchingWorkflow,
    JobSearchWorkflow,
    ResumeBatchGenerationWorkflow,
    ResumeGenerationJobDataError,
    ResumeGenerationJobNotFoundError,
    ResumeGenerationNotEligibleError,
    ResumeGenerationWorkflow,
)


@dataclass(frozen=True, slots=True)
class JobAgentContainer:
    settings: Settings
    database: Database
    company_prospects: CompanyProspectRepository
    crawl_pages: CrawlPageRepository
    company_crawler: GreenhouseCompanyCrawler
    job_prospects: JobProspectRepository
    resume_knowledge: ResumeKnowledgeRepository
    resume_knowledge_service: ResumeKnowledgeService
    job_search_workflow: JobSearchWorkflow
    job_matching_workflow: JobMatchingWorkflow
    resume_generation_workflow: ResumeGenerationWorkflow
    resume_batch_generation_workflow: ResumeBatchGenerationWorkflow


def build_container(
    settings: Settings | None = None,
    *,
    greenhouse_board_limit: int | None = None,
    rotate_greenhouse_boards: bool = False,
) -> JobAgentContainer:
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

    company_prospects = CompanyProspectRepository(database)
    discovery_cursors = CrawlDiscoveryCursorRepository(database)
    crawl_pages = CrawlPageRepository(database)
    job_prospects = JobProspectRepository(database)
    resume_knowledge = ResumeKnowledgeRepository(database)
    resume_knowledge_service = ResumeKnowledgeService(settings.candidate_profile_path)
    notifications = LoggingNotificationService()
    crawler_http = ThrottledHttpClient(
        http=RequestsHttpClient(
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.http_user_agent,
        ),
        interval_seconds=settings.company_crawler_request_delay_seconds,
    )
    company_crawler = GreenhouseCompanyCrawler(
        discovery=GreenhouseCdxDiscovery(
            http=crawler_http,
            cursors=discovery_cursors,
            scan_limit=settings.company_crawler_scan_limit,
            request_delay_seconds=0,
        ),
        boards=GreenhousePublicBoardLookup(http=crawler_http),
        repository=company_prospects,
        crawl_pages=crawl_pages,
        enabled=settings.company_crawler_enabled,
        concurrency=settings.company_crawler_concurrency,
        failed_retry_after=timedelta(
            hours=settings.company_crawler_failed_retry_hours
        ),
    )

    try:
        skill_vocabulary = resume_knowledge_service.load().all_skills
    except ResumeKnowledgeError as error:
        logging.getLogger(__name__).warning(
            "Resume knowledge unavailable for job normalization: %s",
            error,
        )
        skill_vocabulary = ()
    board_limit = (
        settings.greenhouse_board_limit
        if greenhouse_board_limit is None
        else greenhouse_board_limit
    )
    configured_board_tokens = {
        target.value.strip().casefold()
        for target in settings.greenhouse_boards
        if target.value.strip()
    }
    stored_board_limit = max(0, board_limit - len(configured_board_tokens))
    if stored_board_limit and rotate_greenhouse_boards:
        stored_greenhouse_prospects = company_prospects.reserve_for_job_search(
            limit=stored_board_limit
        )
    elif stored_board_limit:
        stored_greenhouse_prospects = company_prospects.list_all(
            limit=stored_board_limit
        )
    else:
        stored_greenhouse_prospects = ()
    job_sources = build_job_sources(
        settings,
        skill_vocabulary=skill_vocabulary,
        greenhouse_boards=tuple(
            GreenhouseBoard(prospect.company_name, prospect.board_token)
            for prospect in stored_greenhouse_prospects
        ),
        greenhouse_board_limit=board_limit,
    )

    search_agent = SearchAgent(
        sources=job_sources,
        repository=job_prospects,
        enabled=settings.search_enabled,
    )
    parser_agent = ParserAgent()
    llm = (
        GeminiLLMService(
            GeminiConfig(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
            )
        )
        if settings.gemini_api_key
        else DisabledLLMService()
    )
    matching_agent = MatchingAgent(
        llm=llm,
        prompt_template=settings.matching_prompt_path.read_text(encoding="utf-8"),
        concurrency=settings.matching_concurrency,
    )
    resume_generator = (
        OpenAIResumeGenerator(
            OpenAIResumeConfig(
                api_key=settings.openai_api_key,
                timeout_seconds=settings.resume_generation_timeout_seconds,
                max_output_tokens=settings.resume_generation_max_output_tokens,
            )
        )
        if settings.openai_api_key
        else DisabledResumeGenerator()
    )
    resume_generation_agent = ResumeGenerationAgent(
        generator=resume_generator,
        documents=DocumentService(settings.generated_documents_dir),
        prompt_template=settings.resume_generation_prompt_path.read_text(
            encoding="utf-8"
        ),
    )
    resume_generation_workflow = ResumeGenerationWorkflow(
        repository=job_prospects,
        agent=resume_generation_agent,
    )
    return JobAgentContainer(
        settings=settings,
        database=database,
        company_prospects=company_prospects,
        crawl_pages=crawl_pages,
        company_crawler=company_crawler,
        job_prospects=job_prospects,
        resume_knowledge=resume_knowledge,
        resume_knowledge_service=resume_knowledge_service,
        job_search_workflow=JobSearchWorkflow(
            search_agent=search_agent,
            parser_agent=parser_agent,
        ),
        job_matching_workflow=JobMatchingWorkflow(
            repository=job_prospects,
            parser_agent=parser_agent,
            matching_agent=matching_agent,
            notifications=notifications,
            resume_candidate_threshold=settings.resume_candidate_threshold,
            resume_generation_model=settings.resume_generation_model,
            max_requests_per_run=settings.matching_max_requests_per_run,
        ),
        resume_generation_workflow=resume_generation_workflow,
        resume_batch_generation_workflow=ResumeBatchGenerationWorkflow(
            repository=job_prospects,
            resume_generation=resume_generation_workflow,
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
        "--match-prospects",
        action="store_true",
        help="score stored job prospects that do not have a match",
    )
    parser.add_argument(
        "--generate-resume",
        metavar="JOB_ID",
        help="generate one resume for a job marked as a resume candidate",
    )
    parser.add_argument(
        "--generate-matched-resumes",
        action="store_true",
        help="generate resumes for matched candidates without a stored filename",
    )
    parser.add_argument(
        "--resume-format",
        choices=("html", "docx", "both"),
        help="generated format; defaults to html for one job and docx for a batch",
    )
    parser.add_argument(
        "--resume-limit",
        type=int,
        default=settings.resume_generation_batch_limit if settings else 1,
        help="maximum queued resumes to generate, up to 100",
    )
    parser.add_argument(
        "--match-limit",
        type=int,
        default=settings.matching_max_requests_per_run if settings else 15,
        help="maximum unmatched prospects to score, up to 15",
    )
    parser.add_argument(
        "--crawl-greenhouse-companies",
        action="store_true",
        help="discover and persist companies with public Greenhouse boards",
    )
    parser.add_argument(
        "--crawl-limit",
        type=int,
        default=100,
        help="maximum Greenhouse boards to validate during one crawl",
    )
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
    parser.add_argument(
        "--greenhouse-board-limit",
        type=int,
        default=settings.greenhouse_board_limit if settings else 25,
        help="maximum Greenhouse boards fetched during one search",
    )
    arguments = parser.parse_args(argv)
    selected_commands = sum(
        (
            arguments.search,
            arguments.match_prospects,
            bool(arguments.generate_resume),
            arguments.generate_matched_resumes,
            arguments.crawl_greenhouse_companies,
        )
    )
    if selected_commands > 1:
        parser.error(
            "--search, --match-prospects, --generate-resume, "
            "--generate-matched-resumes, and "
            "--crawl-greenhouse-companies "
            "cannot be combined"
        )
    if not 1 <= arguments.match_limit <= 15:
        parser.error("--match-limit must be between 1 and 15")
    if not 1 <= arguments.resume_limit <= 100:
        parser.error("--resume-limit must be between 1 and 100")
    if not 1 <= arguments.greenhouse_board_limit <= 1_000:
        parser.error("--greenhouse-board-limit must be between 1 and 1000")
    if arguments.dry_run and not arguments.search:
        parser.error("--dry-run requires --search")
    if arguments.resume_format and not (
        arguments.generate_resume or arguments.generate_matched_resumes
    ):
        parser.error(
            "--resume-format requires --generate-resume or "
            "--generate-matched-resumes"
        )
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
        ("Posted", 10),
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
            job.posted_at.date().isoformat() if job.posted_at else "Unknown",
            job.source,
            job.url,
        )
        for index, (job, match) in enumerate(ranked, 1)
    ]
    return _format_grid(columns, rows)


def _format_search_job_grid(jobs: Sequence[JobPosting]) -> str:
    columns = (
        ("#", 3),
        ("Title", 28),
        ("Company", 22),
        ("Location", 22),
        ("Salary", 22),
        ("Posted", 10),
        ("Source", 12),
        ("URL", 44),
    )
    rows = [
        (
            str(index),
            job.title,
            job.company,
            job.location or "Not provided",
            _format_salary(job),
            job.posted_at.date().isoformat() if job.posted_at else "Unknown",
            job.source,
            job.url,
        )
        for index, job in enumerate(jobs, 1)
    ]
    return _format_grid(columns, rows)


def _format_company_grid(companies: Sequence[CompanyProspect]) -> str:
    columns = (
        ("#", 3),
        ("Company", 36),
        ("Board token", 28),
        ("Company URL", 64),
    )
    rows = [
        (
            str(index),
            company.company_name,
            company.board_token,
            company.company_url,
        )
        for index, company in enumerate(companies, 1)
    ]
    return _format_grid(columns, rows)


def _format_grid(
    columns: Sequence[tuple[str, int]],
    rows: Sequence[Sequence[str]],
) -> str:
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
    container: JobAgentContainer,
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
    result = await container.job_search_workflow.run(criteria)
    print(
        f"Found {result.search.fetched_count} jobs; "
        f"stored {result.search.stored_count}; "
        f"{len(result.search.failures)} source requests failed."
    )
    print(_format_search_job_grid(result.jobs))
    for failure in result.search.failures:
        logging.getLogger(__name__).warning(
            "source=%s query=%s error=%s: %s",
            failure.source,
            failure.query.text,
            failure.error_type,
            failure.message,
        )
    return 0 if result.jobs or not result.search.failures else 1


async def _run_prospect_matching(
    container: JobAgentContainer,
    *,
    limit: int,
) -> int:
    if not container.settings.gemini_api_key:
        logging.getLogger(__name__).error(
            "Job matching requires GEMINI_API_KEY to be configured"
        )
        return 1
    candidate = _load_candidate(container.settings.candidate_profile_path)
    knowledge = container.resume_knowledge_service.load()
    result = await container.job_matching_workflow.run(
        candidate,
        knowledge,
        limit=limit,
    )
    ranked = sorted(
        zip(result.jobs, result.matches),
        key=lambda item: item[1].score,
        reverse=True,
    )
    print(
        f"Matched {len(result.matches)} stored prospects; "
        f"{len(result.resume_candidates)} resume candidates; "
        f"{len(result.failures)} failed."
    )
    print(_format_job_grid(ranked))
    for failure in result.failures:
        logging.getLogger(__name__).warning(
            "job_id=%s title=%s error=%s: %s",
            failure.job.job_id,
            failure.job.title,
            failure.error_type,
            failure.message,
        )
    return 0 if result.matches or not result.failures else 1


async def _run_resume_generation(
    container: JobAgentContainer,
    *,
    job_id: str,
    document_format: str = "html",
) -> int:
    if not container.settings.openai_api_key:
        logging.getLogger(__name__).error(
            "Resume generation requires OPENAI_API_KEY to be configured"
        )
        return 1
    try:
        candidate = _load_candidate(container.settings.candidate_profile_path)
        knowledge = container.resume_knowledge_service.load()
        result = await container.resume_generation_workflow.run(
            job_id=job_id,
            candidate=candidate,
            knowledge=knowledge,
            document_format=document_format,
        )
    except (
        ResumeGenerationJobDataError,
        ResumeGenerationJobNotFoundError,
        ResumeGenerationNotEligibleError,
        ResumeGenerationNotConfiguredError,
        ResumeGenerationResponseError,
        ResumeKnowledgeError,
        MissingDocxDependencyError,
        MissingOpenAIDependencyError,
        TypeError,
        ValueError,
    ) as error:
        logging.getLogger(__name__).error("Resume generation failed: %s", error)
        return 1

    print(f"Generated resume for {result.job.title} at {result.job.company}.")
    print(f"Job ID: {result.job.job_id}")
    print(f"Model: {result.model}")
    for artifact in result.artifacts:
        suffix = Path(artifact.path).suffix.removeprefix(".").upper()
        print(f"Saved ({suffix}): {artifact.path}")
    return 0


async def _run_matched_resume_generation(
    container: JobAgentContainer,
    *,
    limit: int,
    document_format: str,
) -> int:
    if not container.settings.openai_api_key:
        logging.getLogger(__name__).error(
            "Resume generation requires OPENAI_API_KEY to be configured"
        )
        return 1
    try:
        candidate = _load_candidate(container.settings.candidate_profile_path)
        knowledge = container.resume_knowledge_service.load()
        result = await container.resume_batch_generation_workflow.run(
            candidate=candidate,
            knowledge=knowledge,
            limit=limit,
            document_format=document_format,
        )
    except (
        ResumeGenerationNotConfiguredError,
        ResumeKnowledgeError,
        MissingDocxDependencyError,
        MissingOpenAIDependencyError,
        TypeError,
        ValueError,
    ) as error:
        logging.getLogger(__name__).error(
            "Matched resume generation failed: %s",
            error,
        )
        return 1

    print(
        f"Selected {len(result.selected)} queued resume candidates; "
        f"generated {len(result.generated)}; "
        f"failed {len(result.failures)}."
    )
    for generated in result.generated:
        print(
            f"Generated {generated.job.job_id}: "
            f"{generated.prospect.resume_file_name}"
        )
        for artifact in generated.artifacts:
            print(f"  Saved: {artifact.path}")
    for failure in result.failures:
        logging.getLogger(__name__).error(
            "job_id=%s title=%s error=%s: %s",
            failure.prospect.job_id,
            failure.prospect.title,
            failure.error_type,
            failure.message,
        )
    return 0 if not result.failures else 1


async def _run_company_crawl(
    container: JobAgentContainer,
    *,
    limit: int,
) -> int:
    try:
        result = await container.company_crawler.crawl(limit=limit)
    except (
        CompanyCrawlerDisabledError,
        CompanyDiscoveryError,
        HttpRequestError,
        ValueError,
    ) as error:
        logging.getLogger(__name__).error("Greenhouse company crawl failed: %s", error)
        return 1

    print(
        f"Discovered {result.discovered_count} index candidates; "
        f"new {result.new_count}; "
        f"known {result.known_count}; "
        f"retry ready {result.retry_ready_count}; "
        f"retry cooldown {result.retry_deferred_count}; "
        f"checked {result.checked_count}; "
        f"retried {result.retried_count}; "
        f"inserted {result.inserted_count}; "
        f"failed {len(result.failures)}."
    )
    print(_format_company_grid(result.companies))
    for failure in result.failures:
        logging.getLogger(__name__).warning(
            "Greenhouse board %s failed validation: %s",
            failure.board_token,
            failure.message,
        )
    return 0 if result.companies or not result.failures else 1


def main(argv: Sequence[str] | None = None) -> int:
    settings = Settings.from_env()
    arguments = _arguments(argv, settings=settings)
    configure_logging(settings.log_level)
    if arguments.search and arguments.dry_run:
        return _run_apify_dry_run(settings, arguments)
    requested_sources = {
        source.strip().casefold() for source in arguments.source if source.strip()
    }
    searches_greenhouse = arguments.search and (
        not requested_sources or "greenhouse" in requested_sources
    )
    container = build_container(
        settings,
        greenhouse_board_limit=arguments.greenhouse_board_limit,
        rotate_greenhouse_boards=searches_greenhouse,
    )
    logging.getLogger(__name__).info(
        "Job Agent Phase 3 initialized "
        "(search=%s, database=%s@%s:%s/%s)",
        settings.search_enabled,
        settings.mysql_user,
        settings.mysql_host,
        settings.mysql_port,
        settings.mysql_database,
    )
    if arguments.crawl_greenhouse_companies:
        return asyncio.run(
            _run_company_crawl(
                container,
                limit=arguments.crawl_limit,
            )
        )
    if arguments.match_prospects:
        return asyncio.run(
            _run_prospect_matching(
                container,
                limit=arguments.match_limit,
            )
        )
    if arguments.generate_resume:
        return asyncio.run(
            _run_resume_generation(
                container,
                job_id=arguments.generate_resume,
                document_format=arguments.resume_format or "html",
            )
        )
    if arguments.generate_matched_resumes:
        return asyncio.run(
            _run_matched_resume_generation(
                container,
                limit=arguments.resume_limit,
                document_format=(
                    arguments.resume_format
                    or settings.resume_generation_batch_format
                ),
            )
        )
    if arguments.search:
        return asyncio.run(_run_search(container, arguments))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
