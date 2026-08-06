"""Persistence repositories for domain models."""

from .application_repository import ApplicationRepository
from .candidate_repository import CandidateRepository
from .job_prospect_repository import JobProspectRepository
from .resume_repository import ResumeKnowledgeRepository

__all__ = [
    "ApplicationRepository",
    "CandidateRepository",
    "JobProspectRepository",
    "ResumeKnowledgeRepository",
]
