"""Generate a truthful, job-specific resume from reviewed candidate evidence."""

from __future__ import annotations

import json

from models import CandidateProfile, DocumentArtifact, JobPosting, ResumeKnowledgeBase
from services import DocumentService, ResumeGenerator


PROMPT_FIELDS = ("candidate_profile", "resume_knowledge", "job_posting")


class ResumeGenerationAgent:
    def __init__(
        self,
        *,
        generator: ResumeGenerator,
        documents: DocumentService,
        prompt_template: str,
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

    async def generate(
        self,
        *,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
        model: str,
    ) -> DocumentArtifact:
        if candidate.candidate_id != knowledge.candidate_id:
            raise ValueError(
                "candidate profile and resume knowledge must have the same candidate_id"
            )
        prompt = self._render_prompt(candidate, knowledge, job)
        content = await self._generator.generate_resume(prompt, model=model)
        return self._documents.save_text(
            kind="tailored-resume",
            name=f"{candidate.candidate_id}-{job.job_id}",
            content=content.rstrip() + "\n",
        )

    def _render_prompt(
        self,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
    ) -> str:
        candidate_evidence = {
            "full_name": candidate.full_name,
            "email": candidate.email,
            "location": candidate.location,
            "summary": candidate.summary,
            "skills": list(candidate.skills),
            "years_experience": candidate.years_experience,
        }
        job_evidence = {
            "title": job.title,
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
            "resume_knowledge": knowledge.to_dict(),
            "job_posting": job_evidence,
        }
        for field, value in replacements.items():
            rendered = rendered.replace(
                "{" + field + "}",
                json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
            )
        return rendered
