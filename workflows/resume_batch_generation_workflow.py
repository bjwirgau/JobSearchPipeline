"""Generate missing resume and cover-letter packages for eligible jobs."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from models import (
    CandidateProfile,
    JobProspect,
    ResumeDocumentFormat,
    ResumeKnowledgeBase,
)
from repositories import JobProspectRepository

from .resume_generation_workflow import (
    ResumeGenerationWorkflow,
    ResumeGenerationWorkflowResult,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResumeBatchGenerationFailure:
    prospect: JobProspect
    error_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ResumeBatchGenerationWorkflowResult:
    selected: tuple[JobProspect, ...]
    generated: tuple[ResumeGenerationWorkflowResult, ...]
    failures: tuple[ResumeBatchGenerationFailure, ...]


class ResumeBatchGenerationWorkflow:
    def __init__(
        self,
        *,
        repository: JobProspectRepository,
        resume_generation: ResumeGenerationWorkflow,
    ) -> None:
        self._repository = repository
        self._resume_generation = resume_generation

    async def run(
        self,
        *,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        limit: int = 1,
        document_format: ResumeDocumentFormat | str = ResumeDocumentFormat.DOCX,
    ) -> ResumeBatchGenerationWorkflowResult:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        resolved_format = ResumeDocumentFormat.parse(document_format)
        selected = self._repository.list_pending_resume_generation_candidates(
            limit=limit
        )
        generated: list[ResumeGenerationWorkflowResult] = []
        failures: list[ResumeBatchGenerationFailure] = []
        for prospect in selected:
            LOGGER.info(
                "Generating queued document package: job_id=%s match=%.2f title=%s",
                prospect.job_id,
                prospect.match or 0,
                prospect.title,
            )
            try:
                self._repository.record_resume_generation_attempt(prospect.job_id)
                result = await self._resume_generation.run(
                    job_id=prospect.job_id,
                    candidate=candidate,
                    knowledge=knowledge,
                    document_format=resolved_format,
                )
            except Exception as error:
                LOGGER.exception(
                    "Queued document generation failed: job_id=%s title=%s",
                    prospect.job_id,
                    prospect.title,
                )
                failures.append(
                    ResumeBatchGenerationFailure(
                        prospect=prospect,
                        error_type=type(error).__name__,
                        message=str(error),
                    )
                )
                continue
            generated.append(result)
        return ResumeBatchGenerationWorkflowResult(
            selected=selected,
            generated=tuple(generated),
            failures=tuple(failures),
        )
