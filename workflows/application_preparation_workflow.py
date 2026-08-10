"""Fill a generated-resume job application and stop before submission."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agents import ApplicationFormAgent
from browser import ApplicationBrowser, ApplicationBrowserSession
from models import (
    ApplicationFieldKind,
    ApplicationFormField,
    CandidateProfile,
    JobPosting,
    JobProspect,
    ResumeKnowledgeBase,
)
from repositories import JobProspectRepository


LOGGER = logging.getLogger(__name__)


class ApplicationProspectNotFoundError(LookupError):
    pass


class ApplicationResumeNotFoundError(LookupError):
    pass


class ApplicationJobDataError(ValueError):
    pass


class ApplicationFormNotFoundError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class ApplicationPreparationResult:
    prospect: JobProspect
    job: JobPosting
    resume_path: Path
    session: ApplicationBrowserSession
    steps_completed: int
    filled_field_ids: tuple[str, ...]
    unresolved_fields: tuple[ApplicationFormField, ...]
    failures: tuple[str, ...]
    resume_uploaded: bool
    submission_controls_disabled: int

    @property
    def complete(self) -> bool:
        return (
            self.resume_uploaded
            and not any(field.required for field in self.unresolved_fields)
            and not self.failures
        )


class ApplicationPreparationWorkflow:
    def __init__(
        self,
        *,
        repository: JobProspectRepository,
        form_agent: ApplicationFormAgent,
        browser: ApplicationBrowser,
        generated_documents_dir: Path,
        max_steps: int = 10,
    ) -> None:
        if not 1 <= max_steps <= 15:
            raise ValueError("application max steps must be between 1 and 15")
        self._repository = repository
        self._form_agent = form_agent
        self._browser = browser
        self._generated_documents_dir = generated_documents_dir
        self._max_steps = max_steps

    async def run(
        self,
        *,
        job_id: str,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
    ) -> ApplicationPreparationResult:
        prospect = self._load_prospect(job_id)
        resume_path = self._resume_path(prospect)
        job = self._repository.get_job_posting(prospect.job_id)
        if job is None:
            raise ApplicationJobDataError(
                f"job prospect {prospect.job_id} has no normalized job data"
            )
        session = self._browser.open(prospect.url)
        try:
            filled: list[str] = []
            unresolved: dict[str, ApplicationFormField] = {}
            failures: list[str] = []
            resume_uploaded = False
            submission_controls_disabled = 0
            steps_completed = 0
            start_attempted = False
            form_seen = False
            for _ in range(self._max_steps):
                submission_controls_disabled += session.disable_submission()
                if not start_attempted:
                    start_attempted = True
                    if session.open_application_form():
                        continue
                fields = session.inspect_fields()
                if not fields:
                    if not form_seen:
                        raise ApplicationFormNotFoundError(
                            "no application form fields were found on the job page"
                        )
                    break
                form_seen = True
                answer_result = await self._form_agent.answer(
                    fields=fields,
                    candidate=candidate,
                    knowledge=knowledge,
                    job=job,
                )
                fill_result = session.fill_fields(
                    answer_result.answers,
                    resume_path=resume_path,
                )
                self._log_form_answers(
                    job_id=prospect.job_id,
                    step=steps_completed + 1,
                    fields=fields,
                    answers=answer_result.answers,
                    filled_field_ids=fill_result.filled_field_ids,
                    unresolved_fields=(
                        *answer_result.unresolved_fields,
                        *fill_result.unresolved_required_fields,
                    ),
                    resume_path=resume_path,
                    resume_uploaded=fill_result.resume_uploaded,
                )
                filled.extend(fill_result.filled_field_ids)
                resume_uploaded = resume_uploaded or fill_result.resume_uploaded
                failures.extend(fill_result.failures)
                unresolved.update(
                    {
                        field.field_id: field
                        for field in answer_result.unresolved_fields
                    }
                )
                unresolved.update(
                    {
                        field.field_id: field
                        for field in fill_result.unresolved_required_fields
                    }
                )
                steps_completed += 1
                submission_controls_disabled += session.disable_submission()
                has_required_unresolved = any(
                    field.required for field in unresolved.values()
                )
                if has_required_unresolved or failures or not session.advance():
                    break
            else:
                failures.append(
                    f"application exceeded the {self._max_steps}-step safety limit"
                )
            if not resume_uploaded:
                failures.append("the generated resume was not uploaded")
            submission_controls_disabled += session.disable_submission()
            return ApplicationPreparationResult(
                prospect=prospect,
                job=job,
                resume_path=resume_path,
                session=session,
                steps_completed=steps_completed,
                filled_field_ids=tuple(dict.fromkeys(filled)),
                unresolved_fields=tuple(unresolved.values()),
                failures=tuple(dict.fromkeys(failures)),
                resume_uploaded=resume_uploaded,
                submission_controls_disabled=submission_controls_disabled,
            )
        except Exception:
            session.close()
            raise

    @staticmethod
    def _log_form_answers(
        *,
        job_id: str,
        step: int,
        fields: tuple[ApplicationFormField, ...],
        answers: Mapping[str, str],
        filled_field_ids: tuple[str, ...],
        unresolved_fields: tuple[ApplicationFormField, ...],
        resume_path: Path,
        resume_uploaded: bool,
    ) -> None:
        filled_ids = set(filled_field_ids)
        unresolved_ids = {field.field_id for field in unresolved_fields}
        for field in fields:
            source: str | None = None
            value: str | None = None
            if field.field_id in answers:
                source = "agent"
                value = answers[field.field_id]
            elif field.current_value:
                source = "existing"
                value = field.current_value
            elif (
                field.kind is ApplicationFieldKind.FILE
                and field.field_id in filled_ids
                and resume_uploaded
            ):
                source = "resume"
                value = resume_path.name

            if value is not None:
                status = "filled" if field.field_id in filled_ids else "present"
                if source == "agent" and field.field_id not in filled_ids:
                    status = "not_filled"
                LOGGER.info(
                    "event=application_form_answer job_id=%r step=%d "
                    "field_id=%r label=%r source=%s status=%s value=%r",
                    job_id,
                    step,
                    field.field_id,
                    field.label,
                    source,
                    status,
                    value,
                )
            elif field.field_id in unresolved_ids:
                LOGGER.info(
                    "event=application_form_unresolved job_id=%r step=%d "
                    "field_id=%r label=%r required=%s",
                    job_id,
                    step,
                    field.field_id,
                    field.label,
                    field.required,
                )

    def _load_prospect(self, job_id: str) -> JobProspect:
        resolved_job_id = job_id.strip()
        if not resolved_job_id:
            raise ValueError("job_id must not be empty")
        prospect = self._repository.get(resolved_job_id)
        if prospect is None:
            raise ApplicationProspectNotFoundError(
                f"job prospect not found: {resolved_job_id}"
            )
        if not prospect.resume_file_name:
            raise ApplicationResumeNotFoundError(
                f"job prospect {resolved_job_id} has no generated resume"
            )
        return prospect

    def _resume_path(self, prospect: JobProspect) -> Path:
        root = self._generated_documents_dir.resolve()
        path = (root / (prospect.resume_file_name or "")).resolve()
        if path.parent != root:
            raise ApplicationResumeNotFoundError(
                "stored resume filename resolves outside generated documents"
            )
        if not path.is_file():
            raise ApplicationResumeNotFoundError(
                f"generated resume file does not exist: {path.name}"
            )
        if path.suffix.casefold() not in {".docx", ".pdf"}:
            raise ApplicationResumeNotFoundError(
                "application resume must be a DOCX or PDF file; regenerate it "
                "with --resume-format docx"
            )
        return path
