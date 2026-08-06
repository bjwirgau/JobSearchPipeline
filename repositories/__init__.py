"""Persistence repositories for domain models."""

from .application_repository import ApplicationRepository
from .candidate_repository import CandidateRepository
from .company_prospect_repository import CompanyProspectRepository
from .crawl_page_repository import CrawlPageRepository
from .job_prospect_repository import JobProspectRepository
from .resume_repository import ResumeKnowledgeRepository

__all__ = [
    "ApplicationRepository",
    "CandidateRepository",
    "CompanyProspectRepository",
    "CrawlPageRepository",
    "JobProspectRepository",
    "ResumeKnowledgeRepository",
]
