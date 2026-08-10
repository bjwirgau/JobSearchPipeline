"""Shared domain models for the job-agent pipeline."""

from .application import (
    Application,
    ApplicationStatus,
    ApplicationValidation,
    DocumentArtifact,
)
from .application_form import (
    ApplicationFieldKind,
    ApplicationFillResult,
    ApplicationFormField,
)
from .candidate import CandidateProfile
from .crawl_discovery_cursor import CrawlDiscoveryCursor
from .company_prospect import CompanyProspect
from .crawl_page import CrawlPage, CrawlPageType, CrawlStatus
from .job import (
    JobPosting,
    SearchCriteria,
    SearchFailure,
    SearchQuery,
    SearchRunResult,
)
from .job_prospect import (
    DEFAULT_RESUME_CANDIDATE_THRESHOLD,
    DEFAULT_RESUME_GENERATION_MODEL,
    JobProspect,
)
from .generated_resume import (
    GeneratedResumeContent,
    GeneratedResumeRole,
    InvalidGeneratedResumeError,
    ResumeDocumentFormat,
)
from .match import MatchBreakdown, MatchResult
from .resume import (
    ResumeAchievement,
    ResumeCertification,
    ResumeEducation,
    ResumeKnowledgeBase,
    ResumeRole,
)
from .workflow import StageRecord, WorkflowRun, WorkflowStage, WorkflowStatus

__all__ = [
    "Application",
    "ApplicationFieldKind",
    "ApplicationFillResult",
    "ApplicationFormField",
    "ApplicationStatus",
    "ApplicationValidation",
    "CandidateProfile",
    "CrawlDiscoveryCursor",
    "CompanyProspect",
    "CrawlPage",
    "CrawlPageType",
    "CrawlStatus",
    "DocumentArtifact",
    "DEFAULT_RESUME_CANDIDATE_THRESHOLD",
    "DEFAULT_RESUME_GENERATION_MODEL",
    "GeneratedResumeContent",
    "GeneratedResumeRole",
    "InvalidGeneratedResumeError",
    "JobPosting",
    "JobProspect",
    "MatchBreakdown",
    "MatchResult",
    "ResumeAchievement",
    "ResumeCertification",
    "ResumeDocumentFormat",
    "ResumeEducation",
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
