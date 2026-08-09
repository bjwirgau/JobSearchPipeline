"""Generate one resume for a stored job explicitly marked as eligible."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agents import ResumeGenerationAgent
from models import (
    CandidateProfile,
    DocumentArtifact,
    JobPosting,
    JobProspect,
    ResumeKnowledgeBase,
)
from repositories import JobProspectRepository


LOGGER = logging.getLogger(__name__)


class ResumeGenerationJobNotFoundError(LookupError):
    pass


class ResumeGenerationNotEligibleError(ValueError):
    pass


class ResumeGenerationJobDataError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResumeGenerationWorkflowResult:
    prospect: JobProspect
    job: JobPosting
    artifact: DocumentArtifact
    model: str


class ResumeGenerationWorkflow:
    def __init__(
        self,
        *,
        repository: JobProspectRepository,
        agent: ResumeGenerationAgent,
    ) -> None:
        self._repository = repository
        self._agent = agent

    async def run(
        self,
        *,
        job_id: str,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
    ) -> ResumeGenerationWorkflowResult:
        resolved_job_id = job_id.strip()
        if not resolved_job_id:
            raise ValueError("job_id must not be empty")
        prospect = self._repository.get(resolved_job_id)
        if prospect is None:
            raise ResumeGenerationJobNotFoundError(
                f"job prospect not found: {resolved_job_id}"
            )
        if not (
            prospect.resume_generation_checked
            and prospect.resume_generation_candidate
            and prospect.resume_generation_model
        ):
            raise ResumeGenerationNotEligibleError(
                f"job prospect {resolved_job_id} is not marked for resume generation"
            )
        job = self._repository.get_job_posting(resolved_job_id)
        if job is None:
            raise ResumeGenerationJobDataError(
                f"job prospect {resolved_job_id} has no normalized job data"
            )
        LOGGER.info(
            "Generating resume: job_id=%s title=%s company=%s model=%s",
            job.job_id,
            job.title,
            job.company,
            prospect.resume_generation_model,
        )
        artifact = await self._agent.generate(
            candidate=candidate,
            knowledge=knowledge,
            job=job,
            model=prospect.resume_generation_model,
        )
        return ResumeGenerationWorkflowResult(
            prospect=prospect,
            job=job,
            artifact=artifact,
            model=prospect.resume_generation_model,
        )
