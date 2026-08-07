"""Evidence-grounded LLM matching for candidate and job records."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

from models import (
    CandidateProfile,
    JobPosting,
    MatchBreakdown,
    MatchResult,
    ResumeKnowledgeBase,
)
from services import LLMService
from utils.text import normalize_text


MATCH_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "breakdown": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "skills": {"type": "number", "minimum": 0, "maximum": 1},
                "title": {"type": "number", "minimum": 0, "maximum": 1},
                "location": {"type": "number", "minimum": 0, "maximum": 1},
                "experience": {"type": "number", "minimum": 0, "maximum": 1},
                "industry": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["skills", "title", "location", "experience", "industry"],
        },
        "matched_skills": {
            "type": "array",
            "items": {"type": "string"},
        },
        "missing_skills": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rationale": {"type": "string", "minLength": 1, "maxLength": 1_200},
    },
    "required": [
        "score",
        "breakdown",
        "matched_skills",
        "missing_skills",
        "rationale",
    ],
}

PROMPT_FIELDS = ("candidate_profile", "resume_knowledge", "job_posting")


class InvalidMatchResponseError(ValueError):
    pass


class MatchingAgent:
    def __init__(
        self,
        *,
        llm: LLMService,
        prompt_template: str,
        concurrency: int = 5,
    ) -> None:
        if concurrency <= 0:
            raise ValueError("matching concurrency must be greater than zero")
        missing_fields = [
            field for field in PROMPT_FIELDS if "{" + field + "}" not in prompt_template
        ]
        if missing_fields:
            raise ValueError(
                "match prompt is missing placeholders: " + ", ".join(missing_fields)
            )
        self._llm = llm
        self._prompt_template = prompt_template
        self._request_limit = asyncio.Semaphore(concurrency)

    async def score(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        resume_knowledge: ResumeKnowledgeBase | None = None,
    ) -> MatchResult:
        prompt = self._render_prompt(candidate, job, resume_knowledge)
        async with self._request_limit:
            response = await self._llm.generate_structured(
                prompt,
                schema=MATCH_SCHEMA,
            )
        return self._to_match_result(candidate, job, resume_knowledge, response)

    def _render_prompt(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        resume_knowledge: ResumeKnowledgeBase | None,
    ) -> str:
        evidence = {
            "summary": candidate.summary,
            "skills": list(candidate.skills),
            "years_experience": candidate.years_experience,
            "current_location": candidate.location,
            "desired_titles": list(candidate.desired_titles),
            "desired_locations": list(candidate.desired_locations),
            "remote_preference": candidate.remote_preference,
        }
        knowledge: Mapping[str, object] = {}
        if resume_knowledge is not None:
            knowledge = {
                "skills": list(resume_knowledge.skills),
                "years": dict(resume_knowledge.years),
                "industries": list(resume_knowledge.industries),
                "roles": [role.to_dict() for role in resume_knowledge.roles],
                "achievements": list(resume_knowledge.achievements),
                "certifications": list(resume_knowledge.certifications),
                "education": list(resume_knowledge.education),
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
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "salary_currency": job.salary_currency,
            "is_remote": job.is_remote,
            "remote_country_codes": list(job.remote_country_codes),
        }
        rendered = self._prompt_template
        replacements = {
            "candidate_profile": evidence,
            "resume_knowledge": knowledge,
            "job_posting": job_evidence,
        }
        for field, value in replacements.items():
            rendered = rendered.replace(
                "{" + field + "}",
                json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
            )
        return rendered

    @staticmethod
    def _to_match_result(
        candidate: CandidateProfile,
        job: JobPosting,
        resume_knowledge: ResumeKnowledgeBase | None,
        response: Mapping[str, Any],
    ) -> MatchResult:
        breakdown_value = response.get("breakdown")
        if not isinstance(breakdown_value, Mapping):
            raise InvalidMatchResponseError("match breakdown must be an object")
        breakdown = MatchBreakdown(
            skills=_score(breakdown_value, "skills"),
            title=_score(breakdown_value, "title"),
            location=_score(breakdown_value, "location"),
            experience=_score(breakdown_value, "experience"),
            industry=_score(breakdown_value, "industry"),
        )
        matched_skills = _strings(response, "matched_skills")
        missing_skills = _strings(response, "missing_skills")
        rationale = response.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise InvalidMatchResponseError("match rationale must not be empty")
        skill_years = {
            skill: years
            for skill in matched_skills
            if resume_knowledge
            and (years := resume_knowledge.years_for(skill)) is not None
        }
        return MatchResult(
            candidate_id=candidate.candidate_id,
            job_id=job.job_id,
            score=round(_score(response, "score"), 4),
            breakdown=breakdown,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            skill_years=skill_years,
            rationale=rationale.strip(),
        )


def _score(value: Mapping[str, Any], field: str) -> float:
    raw_score = value.get(field)
    if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
        raise InvalidMatchResponseError(f"{field} score must be numeric")
    score = float(raw_score)
    if not 0 <= score <= 1:
        raise InvalidMatchResponseError(f"{field} score must be between 0 and 1")
    return score


def _strings(value: Mapping[str, Any], field: str) -> tuple[str, ...]:
    items = value.get(field)
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        raise InvalidMatchResponseError(f"{field} must be an array of strings")
    unique: dict[str, str] = {}
    for item in items:
        cleaned = item.strip()
        if cleaned:
            unique.setdefault(normalize_text(cleaned), cleaned)
    return tuple(unique.values())
