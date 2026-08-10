"""Create cover letters for review from candidate and job evidence."""

from __future__ import annotations

import json
from typing import Mapping

from models import (
    CandidateProfile,
    DocumentArtifact,
    GeneratedCoverLetterContent,
    JobPosting,
    MatchResult,
    ResumeDocumentFormat,
    ResumeKnowledgeBase,
)
from services import (
    CoverLetterDocxRenderer,
    CoverLetterHTMLRenderer,
    DocumentService,
    ResumeGenerator,
)


COVER_LETTER_PROMPT_FIELDS = (
    "candidate_profile",
    "resume_knowledge",
    "job_posting",
)


class CoverLetterAgent:
    """Legacy deterministic draft used by the review workflow skeleton."""

    def __init__(self, documents: DocumentService) -> None:
        self._documents = documents

    def draft(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        match: MatchResult,
    ) -> DocumentArtifact:
        strengths = ", ".join(match.matched_skills) or "the role's core requirements"
        content = (
            f"Dear {job.company} hiring team,\n\n"
            f"I am interested in the {job.title} position. My background includes "
            f"{strengths}. I would welcome the opportunity to discuss how my "
            "experience could support your team.\n\n"
            f"Sincerely,\n{candidate.full_name}\n"
        )
        return self._documents.save_text(
            kind="cover-letter-draft",
            name=f"{candidate.candidate_id}-{job.job_id}",
            content=content,
        )


class CoverLetterGenerationAgent:
    """Generate and render an evidence-linked, job-specific cover letter."""

    def __init__(
        self,
        *,
        generator: ResumeGenerator,
        documents: DocumentService,
        prompt_template: str,
        renderer: CoverLetterHTMLRenderer | None = None,
        docx_renderer: CoverLetterDocxRenderer | None = None,
    ) -> None:
        missing_fields = [
            field
            for field in COVER_LETTER_PROMPT_FIELDS
            if "{" + field + "}" not in prompt_template
        ]
        if missing_fields:
            raise ValueError(
                "cover-letter generation prompt is missing placeholders: "
                + ", ".join(missing_fields)
            )
        self._generator = generator
        self._documents = documents
        self._prompt_template = prompt_template
        self._renderer = renderer or CoverLetterHTMLRenderer()
        self._docx_renderer = docx_renderer or CoverLetterDocxRenderer()

    async def generate(
        self,
        *,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
        model: str,
        document_format: ResumeDocumentFormat | str = ResumeDocumentFormat.HTML,
    ) -> tuple[DocumentArtifact, ...]:
        if candidate.candidate_id != knowledge.candidate_id:
            raise ValueError(
                "candidate profile and resume knowledge must have the same candidate_id"
            )
        evidence = self._evidence(candidate, knowledge, job)
        prompt = self._render_prompt(evidence)
        response = await self._generator.generate_cover_letter(prompt, model=model)
        content = GeneratedCoverLetterContent.from_dict(response)
        content.validate_evidence(
            evidence_id
            for group in evidence.values()
            for evidence_id in group
        )

        resolved_format = ResumeDocumentFormat.parse(document_format)
        name = f"{candidate.candidate_id}-{job.job_id}"
        artifacts: list[DocumentArtifact] = []
        if ResumeDocumentFormat.HTML.value in resolved_format.extensions:
            artifacts.append(
                self._documents.save_text(
                    kind="tailored-cover-letter",
                    name=name,
                    content=self._renderer.render(candidate, content, job=job),
                    extension=ResumeDocumentFormat.HTML.value,
                )
            )
        if ResumeDocumentFormat.DOCX.value in resolved_format.extensions:
            artifacts.append(
                self._documents.save_bytes(
                    kind="tailored-cover-letter",
                    name=name,
                    content=self._docx_renderer.render(candidate, content, job=job),
                    extension=ResumeDocumentFormat.DOCX.value,
                )
            )
        return tuple(artifacts)

    def _render_prompt(
        self,
        evidence: Mapping[str, Mapping[str, object]],
    ) -> str:
        rendered = self._prompt_template
        for field in COVER_LETTER_PROMPT_FIELDS:
            rendered = rendered.replace(
                "{" + field + "}",
                json.dumps(
                    evidence[field],
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        return rendered

    @staticmethod
    def _evidence(
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
    ) -> dict[str, dict[str, object]]:
        candidate_evidence: dict[str, object] = {
            "candidate.skills": list(candidate.skills),
            "candidate.additional_keywords": list(candidate.additional_keywords),
            "candidate.years_experience": candidate.years_experience,
        }
        resume_evidence: dict[str, object] = {
            "resume.skills": list(knowledge.skills),
            "resume.skill_years": dict(knowledge.years),
            "resume.industries": list(knowledge.industries),
        }
        resume_evidence.update(
            {
                f"resume.role.{index}": role.to_dict()
                for index, role in enumerate(knowledge.roles)
            }
        )
        resume_evidence.update(
            {
                f"resume.achievement.{index}": achievement.to_dict()
                for index, achievement in enumerate(knowledge.achievements)
            }
        )
        resume_evidence.update(
            {
                f"resume.certification.{index}": certification.to_dict()
                for index, certification in enumerate(knowledge.certifications)
            }
        )
        resume_evidence.update(
            {
                f"resume.education.{index}": education.to_dict()
                for index, education in enumerate(knowledge.education)
            }
        )
        job_evidence: dict[str, object] = {
            "job.title": job.title,
            "job.company": job.company,
            "job.location": job.location,
            "job.description": job.description,
            "job.skills": list(job.skills),
            "job.industries": list(job.industries),
            "job.responsibilities": list(job.responsibilities),
            "job.requirements": list(job.requirements),
            "job.employment_type": job.employment_type,
            "job.is_remote": job.is_remote,
        }
        return {
            "candidate_profile": _without_empty_values(candidate_evidence),
            "resume_knowledge": _without_empty_values(resume_evidence),
            "job_posting": _without_empty_values(job_evidence),
        }


def _without_empty_values(values: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in values.items()
        if value is not None and value != "" and value != [] and value != {}
    }
