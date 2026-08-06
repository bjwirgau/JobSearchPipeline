"""Shared domain models for the job-agent pipeline."""

from .application import (
    Application,
    ApplicationStatus,
    ApplicationValidation,
    DocumentArtifact,
)
from .candidate import CandidateProfile
from .job import (
    JobPosting,
    SearchCriteria,
    SearchFailure,
    SearchQuery,
    SearchRunResult,
)
from .job_prospect import JobProspect
from .match import MatchBreakdown, MatchResult
from .resume import ResumeKnowledgeBase, ResumeRole
from .workflow import StageRecord, WorkflowRun, WorkflowStage, WorkflowStatus

__all__ = [
    "Application",
    "ApplicationStatus",
    "ApplicationValidation",
    "CandidateProfile",
    "DocumentArtifact",
    "JobPosting",
    "JobProspect",
    "MatchBreakdown",
    "MatchResult",
    "ResumeKnowledgeBase",
    "ResumeRole",
    "SearchCriteria",
    "SearchFailure",
    "SearchQuery",
    "SearchRunResult",
    "StageRecord",
    "WorkflowRun",
    "WorkflowStage",
    "WorkflowStatus",
]
