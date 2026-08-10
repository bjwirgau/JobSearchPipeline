"""Evidence-grounded application form answers for a review-only browser session."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from models import (
    ApplicationFieldKind,
    ApplicationFormField,
    CandidateProfile,
    JobPosting,
    ResumeKnowledgeBase,
)
from services import LLMService
from utils.text import normalize_text, tokenize


PROMPT_FIELDS = (
    "candidate_profile",
    "resume_knowledge",
    "job_posting",
    "application_answers",
    "form_fields",
)

RESTRICTED_ANSWER_TERMS = (
    "authorized to work",
    "work authorization",
    "sponsorship",
    "visa",
    "citizenship",
    "race",
    "ethnicity",
    "gender",
    "sex",
    "pronoun",
    "disability",
    "disabled",
    "veteran",
    "military",
    "date of birth",
    "birth date",
    "age",
    "criminal",
    "conviction",
    "salary",
    "compensation",
    "desired pay",
    "start date",
    "available to start",
    "consent",
    "certify",
    "signature",
)


class InvalidApplicationAnswerResponseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ApplicationFormAnswerResult:
    answers: Mapping[str, str]
    unresolved_fields: tuple[ApplicationFormField, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "answers", MappingProxyType(dict(self.answers)))


class ApplicationFormAgent:
    def __init__(self, *, llm: LLMService, prompt_template: str) -> None:
        missing = [
            field
            for field in PROMPT_FIELDS
            if "{" + field + "}" not in prompt_template
        ]
        if missing:
            raise ValueError(
                "application prompt is missing placeholders: " + ", ".join(missing)
            )
        self._llm = llm
        self._prompt_template = prompt_template

    async def answer(
        self,
        *,
        fields: tuple[ApplicationFormField, ...],
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
    ) -> ApplicationFormAnswerResult:
        answers: dict[str, str] = {}
        remaining: list[ApplicationFormField] = []
        for field in fields:
            if field.kind is ApplicationFieldKind.FILE or field.current_value:
                continue
            value = self._local_answer(field, candidate)
            if value is not None:
                answers[field.field_id] = value
            else:
                remaining.append(field)

        llm_fields = tuple(
            field
            for field in remaining
            if not self._is_restricted(field)
        )
        restricted = tuple(
            field
            for field in remaining
            if self._is_restricted(field)
        )
        if llm_fields:
            response = await self._llm.generate_structured(
                self._render_prompt(
                    candidate=candidate,
                    knowledge=knowledge,
                    job=job,
                    fields=llm_fields,
                ),
                schema=_answer_schema(llm_fields),
            )
            llm_answers, llm_unresolved = self._validate_response(
                response,
                llm_fields,
            )
            answers.update(llm_answers)
        else:
            llm_unresolved = ()

        unresolved_by_id = {
            field.field_id: field
            for field in (*restricted, *llm_unresolved)
        }
        return ApplicationFormAnswerResult(
            answers=answers,
            unresolved_fields=tuple(unresolved_by_id.values()),
        )

    def _render_prompt(
        self,
        *,
        candidate: CandidateProfile,
        knowledge: ResumeKnowledgeBase,
        job: JobPosting,
        fields: tuple[ApplicationFormField, ...],
    ) -> str:
        candidate_evidence = {
            "location": candidate.location,
            "summary": candidate.summary,
            "skills": list(candidate.skills),
            "years_experience": candidate.years_experience,
            "additional_keywords": list(candidate.additional_keywords),
        }
        resume_evidence = {
            "skills": list(knowledge.skills),
            "years": dict(knowledge.years),
            "industries": list(knowledge.industries),
            "roles": [role.to_dict() for role in knowledge.roles],
            "education": [value.to_dict() for value in knowledge.education],
            "certifications": [
                value.to_dict() for value in knowledge.certifications
            ],
        }
        job_evidence = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": job.description,
            "requirements": list(job.requirements),
        }
        form_evidence = [
            {
                "field_id": field.field_id,
                "label": field.label,
                "kind": field.kind.value,
                "required": field.required,
                "options": list(field.options),
            }
            for field in fields
        ]
        replacements: Mapping[str, object] = {
            "candidate_profile": candidate_evidence,
            "resume_knowledge": resume_evidence,
            "job_posting": job_evidence,
            "application_answers": dict(candidate.application_answers),
            "form_fields": form_evidence,
        }
        rendered = self._prompt_template
        for field, value in replacements.items():
            rendered = rendered.replace(
                "{" + field + "}",
                json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True),
            )
        return rendered

    @staticmethod
    def _local_answer(
        field: ApplicationFormField,
        candidate: CandidateProfile,
    ) -> str | None:
        label = normalize_text(field.label)
        approved = _approved_answer(label, candidate.application_answers)
        if approved is not None:
            return _canonical_value(field, approved)
        if ApplicationFormAgent._is_restricted(field):
            return None
        if field.kind in {
            ApplicationFieldKind.SELECT,
            ApplicationFieldKind.RADIO,
            ApplicationFieldKind.CHECKBOX,
        }:
            return None
        if "first name" in label or "given name" in label:
            return candidate.full_name.split(maxsplit=1)[0]
        if "last name" in label or "family name" in label or "surname" in label:
            parts = candidate.full_name.rsplit(maxsplit=1)
            return parts[-1]
        if label == "name" or any(
            value in label
            for value in ("full name", "legal name", "candidate name", "applicant name")
        ):
            return candidate.full_name
        if "email" in label:
            return candidate.email
        if "phone" in label or "mobile" in label:
            return candidate.phone or None
        if label == "country" or label.startswith("phone country"):
            return _country_form_value(candidate.country) or None
        if "linkedin" in label:
            return candidate.linkedin_url or None
        if "github" in label:
            return candidate.github_url or None
        if "portfolio" in label or "website" in label or "personal url" in label:
            return candidate.website_url or None
        if (
            label.startswith("location")
            or "current location" in label
            or "city and state" in label
        ):
            return candidate.location or None
        return None

    @staticmethod
    def _is_restricted(field: ApplicationFormField) -> bool:
        label = normalize_text(field.label)
        words = set(tokenize(label))
        return any(
            term in label if " " in term else term in words
            for term in RESTRICTED_ANSWER_TERMS
        )

    @staticmethod
    def _validate_response(
        response: Mapping[str, Any],
        fields: tuple[ApplicationFormField, ...],
    ) -> tuple[dict[str, str], tuple[ApplicationFormField, ...]]:
        raw_answers = response.get("answers")
        raw_unresolved = response.get("unresolved")
        if not isinstance(raw_answers, list):
            raise InvalidApplicationAnswerResponseError(
                "application answers must be an array"
            )
        if not isinstance(raw_unresolved, list) or any(
            not isinstance(value, str) for value in raw_unresolved
        ):
            raise InvalidApplicationAnswerResponseError(
                "unresolved application fields must be an array of IDs"
            )
        fields_by_id = {field.field_id: field for field in fields}
        answers: dict[str, str] = {}
        for value in raw_answers:
            if not isinstance(value, Mapping):
                raise InvalidApplicationAnswerResponseError(
                    "each application answer must be an object"
                )
            field_id = value.get("field_id")
            answer = value.get("value")
            if not isinstance(field_id, str) or field_id not in fields_by_id:
                raise InvalidApplicationAnswerResponseError(
                    "application answer contains an unknown field ID"
                )
            if field_id in answers:
                raise InvalidApplicationAnswerResponseError(
                    f"application answer repeats field ID {field_id}"
                )
            if not isinstance(answer, str) or not answer.strip():
                raise InvalidApplicationAnswerResponseError(
                    f"application answer for {field_id} must not be empty"
                )
            canonical = _canonical_value(fields_by_id[field_id], answer)
            if canonical is None:
                raise InvalidApplicationAnswerResponseError(
                    f"application answer for {field_id} is not a supported option"
                )
            answers[field_id] = canonical
        unresolved_ids = set(raw_unresolved)
        unknown = unresolved_ids - fields_by_id.keys()
        if unknown:
            raise InvalidApplicationAnswerResponseError(
                "unresolved application fields contain unknown IDs"
            )
        unresolved_ids.update(fields_by_id.keys() - answers.keys())
        return answers, tuple(
            fields_by_id[field_id]
            for field_id in fields_by_id
            if field_id in unresolved_ids
        )


def _approved_answer(label: str, answers: Mapping[str, str]) -> str | None:
    for question, answer in answers.items():
        normalized_question = normalize_text(question)
        if (
            normalized_question == label
            or normalized_question in label
            or label in normalized_question
        ):
            return answer
    return None


def _country_form_value(value: str) -> str:
    normalized = value.strip().casefold()
    names = {
        "us": "United States",
        "usa": "United States",
        "u.s.": "United States",
        "gb": "United Kingdom",
        "uk": "United Kingdom",
    }
    return names.get(normalized, value.strip())


def _canonical_value(field: ApplicationFormField, value: str) -> str | None:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        return None
    if field.kind in {ApplicationFieldKind.SELECT, ApplicationFieldKind.RADIO}:
        normalized = normalize_text(cleaned)
        return next(
            (
                option
                for option in field.options
                if normalize_text(option) == normalized
            ),
            None,
        )
    if field.kind is ApplicationFieldKind.CHECKBOX:
        normalized = cleaned.casefold()
        if normalized in {"true", "yes", "1", "checked"}:
            return "true"
        if normalized in {"false", "no", "0", "unchecked"}:
            return "false"
        return None
    return cleaned.replace("\r", " ").replace("\n", " ")


def _answer_schema(
    fields: tuple[ApplicationFormField, ...],
) -> Mapping[str, Any]:
    field_ids = [field.field_id for field in fields]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field_id": {"type": "string", "enum": field_ids},
                        "value": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 4_000,
                        },
                    },
                    "required": ["field_id", "value"],
                },
            },
            "unresolved": {
                "type": "array",
                "items": {"type": "string", "enum": field_ids},
            },
        },
        "required": ["answers", "unresolved"],
    }
