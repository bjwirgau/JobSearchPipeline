"""Generate a truthful, job-specific resume from reviewed candidate evidence."""

from __future__ import annotations

import json

from models import (
    CandidateProfile,
    DocumentArtifact,
    GeneratedResumeContent,
    JobPosting,
    ResumeDocumentFormat,
    ResumeKnowledgeBase,
)
from services import (
    DocumentService,
    ResumeDocxRenderer,
    ResumeGenerator,
    ResumeHTMLRenderer,
)


PROMPT_FIELDS = ("candidate_profile", "resume_knowledge", "job_posting")


class ResumeGenerationAgent:
    def __init__(
        self,
        *,
        generator: ResumeGenerator,
        documents: DocumentService,
        prompt_template: str,
        renderer: ResumeHTMLRenderer | None = None,
        docx_renderer: ResumeDocxRenderer | None = None,
    ) -> None:
        missing_fields = [
            field for field in PROMPT_FIELDS if "{" + field + "}" not in prompt_template
        ]
        if missing_fields:
            raise ValueError(
                "resume generation prompt is missing placeholders: "
                + ", ".join(missing_fields)
            )
        self._generator = generator
        self._documents = documents
        self._prompt_template = prompt_template
        self._renderer = renderer or ResumeHTMLRenderer()
        self._docx_renderer = docx_renderer or ResumeDocxRenderer()

    async def generate(
        self,
        *,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
        target_title: str,
        model: str,
        document_format: ResumeDocumentFormat | str = ResumeDocumentFormat.HTML,
    ) -> tuple[DocumentArtifact, ...]:
        if candidate.candidate_id != knowledge.candidate_id:
            raise ValueError(
                "candidate profile and resume knowledge must have the same candidate_id"
            )
        resolved_target_title = target_title.strip()
        if not resolved_target_title:
            raise ValueError("target resume title must not be empty")
        prompt = self._render_prompt(
            candidate,
            knowledge,
            job,
            target_title=resolved_target_title,
        )
        response = await self._generator.generate_resume(prompt, model=model)
        content = GeneratedResumeContent.from_dict(response)
        content.validate_against(
            knowledge,
            candidate_skills=candidate.skills,
        )
        resolved_format = ResumeDocumentFormat.parse(document_format)
        name = f"{candidate.candidate_id}-{job.job_id}"
        artifacts: list[DocumentArtifact] = []
        if ResumeDocumentFormat.HTML.value in resolved_format.extensions:
            document = self._renderer.render(
                candidate,
                content,
                target_title=resolved_target_title,
            )
            artifacts.append(
                self._documents.save_text(
                    kind="tailored-resume",
                    name=name,
                    content=document,
                    extension=ResumeDocumentFormat.HTML.value,
                )
            )
        if ResumeDocumentFormat.DOCX.value in resolved_format.extensions:
            document = self._docx_renderer.render(
                candidate,
                content,
                target_title=resolved_target_title,
            )
            artifacts.append(
                self._documents.save_bytes(
                    kind="tailored-resume",
                    name=name,
                    content=document,
                    extension=ResumeDocumentFormat.DOCX.value,
                )
            )
        return tuple(artifacts)

    def _render_prompt(
        self,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
        *,
        target_title: str,
    ) -> str:
        candidate_evidence = {
            "skills": list(candidate.skills),
            "years_experience": candidate.years_experience,
        }
        resume_evidence = {
            "skills": list(knowledge.skills),
            "years": dict(knowledge.years),
            "industries": list(knowledge.industries),
            "roles": [role.to_dict() for role in knowledge.roles],
            "achievements": [value.to_dict() for value in knowledge.achievements],
            "certifications": [
                value.to_dict() for value in knowledge.certifications
            ],
            "education": [value.to_dict() for value in knowledge.education],
        }
        job_evidence = {
            "title": target_title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "skills": list(job.skills),
            "industries": list(job.industries),
            "responsibilities": list(job.responsibilities),
            "requirements": list(job.requirements),
            "employment_type": job.employment_type,
            "is_remote": job.is_remote,
        }
        rendered = self._prompt_template
        replacements = {
            "candidate_profile": candidate_evidence,
            "resume_knowledge": resume_evidence,
            "job_posting": job_evidence,
        }
        for field, value in replacements.items():
            rendered = rendered.replace(
                "{" + field + "}",
                json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
            )
        return rendered
