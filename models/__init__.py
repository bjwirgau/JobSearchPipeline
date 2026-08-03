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
from .match import MatchBreakdown, MatchResult
from .workflow import StageRecord, WorkflowRun, WorkflowStage, WorkflowStatus

__all__ = [
    "Application",
    "ApplicationStatus",
    "ApplicationValidation",
    "CandidateProfile",
    "DocumentArtifact",
    "JobPosting",
    "MatchBreakdown",
    "MatchResult",
    "SearchCriteria",
    "SearchFailure",
    "SearchQuery",
    "SearchRunResult",
    "StageRecord",
    "WorkflowRun",
    "WorkflowStage",
    "WorkflowStatus",
]
