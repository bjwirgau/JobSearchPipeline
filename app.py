"""Application composition root for the Phase 2 job-agent foundation."""

from __future__ import annotations

import logging
from dataclasses import dataclass

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
from repositories import (
    ApplicationRepository,
    CandidateRepository,
    JobRepository,
    ResumeKnowledgeRepository,
)
from services import DocumentService, LoggingNotificationService, ResumeKnowledgeService
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

    search_agent = SearchAgent(
        sources=(),
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


def main() -> None:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    build_container(settings)
    logging.getLogger(__name__).info(
        "Job Agent Phase 2 initialized (search=%s, submission=%s, database=%s)",
        settings.search_enabled,
        settings.application_submission_enabled,
        settings.database_path,
    )


if __name__ == "__main__":
    main()
