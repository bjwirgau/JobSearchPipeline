"""Validated content selected by the LLM for a tailored resume."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .resume import (
    ResumeAchievement,
    ResumeCertification,
    ResumeEducation,
    ResumeKnowledgeBase,
    ResumeRole,
)
from utils.text import normalize_text


class InvalidGeneratedResumeError(ValueError):
    pass


class ResumeDocumentFormat(str, Enum):
    HTML = "html"
    DOCX = "docx"
    BOTH = "both"

    @classmethod
    def parse(cls, value: "ResumeDocumentFormat | str") -> "ResumeDocumentFormat":
        if isinstance(value, cls):
            return value
        try:
            return cls(value.strip().casefold())
        except (AttributeError, ValueError) as error:
            supported = ", ".join(member.value for member in cls)
            raise ValueError(
                f"unsupported resume document format; choose from: {supported}"
            ) from error

    @property
    def extensions(self) -> tuple[str, ...]:
        if self is ResumeDocumentFormat.BOTH:
            return (ResumeDocumentFormat.HTML.value, ResumeDocumentFormat.DOCX.value)
        return (self.value,)


def _string(value: object, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        raise InvalidGeneratedResumeError(f"{field} must be a string")
    cleaned = value.strip()
    if required and not cleaned:
        raise InvalidGeneratedResumeError(f"{field} must not be empty")
    return cleaned


def _optional_string(value: object, field: str) -> str | None:
    if value is None:
        return None
    cleaned = _string(value, field, required=False)
    return cleaned or None


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidGeneratedResumeError(f"{field} must be an array")
    values: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = _string(item, f"{field} item")
        normalized = normalize_text(cleaned)
        if normalized not in seen:
            seen.add(normalized)
            values.append(cleaned)
    return tuple(values)


@dataclass(frozen=True, slots=True)
class GeneratedResumeRole:
    company: str
    title: str
    location: str | None
    start_date: str | None
    end_date: str | None
    responsibilities: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedResumeRole":
        return cls(
            company=_string(value.get("company"), "experience company"),
            title=_string(value.get("title"), "experience title"),
            location=_optional_string(value.get("location"), "experience location"),
            start_date=_optional_string(
                value.get("start_date"),
                "experience start_date",
            ),
            end_date=_optional_string(value.get("end_date"), "experience end_date"),
            responsibilities=_strings(
                value.get("responsibilities", value.get("achievements")),
                "experience responsibilities",
            ),
        )


@dataclass(frozen=True, slots=True)
class GeneratedResumeContent:
    professional_summary: str
    target_title: str | None
    skills: tuple[str, ...]
    experience: tuple[GeneratedResumeRole, ...]
    career_highlights: tuple[ResumeAchievement, ...]
    education: tuple[ResumeEducation, ...]
    certifications: tuple[ResumeCertification, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedResumeContent":
        raw_experience = value.get("experience")
        if not isinstance(raw_experience, list):
            raise InvalidGeneratedResumeError("experience must be an array")
        experience: list[GeneratedResumeRole] = []
        for item in raw_experience:
            if not isinstance(item, Mapping):
                raise InvalidGeneratedResumeError(
                    "each experience entry must be an object"
                )
            experience.append(GeneratedResumeRole.from_dict(item))
        return cls(
            professional_summary=_string(
                value.get("professional_summary"),
                "professional_summary",
            ),
            target_title=_optional_string(value.get("target_title"), "target_title"),
            skills=_strings(value.get("skills"), "skills"),
            experience=tuple(experience),
            career_highlights=cls._structured_values(
                value.get("career_highlights"),
                "career_highlights",
                ResumeAchievement.from_value,
            ),
            education=cls._structured_values(
                value.get("education"),
                "education",
                ResumeEducation.from_value,
            ),
            certifications=cls._structured_values(
                value.get("certifications"),
                "certifications",
                ResumeCertification.from_value,
            ),
        )

    @staticmethod
    def _structured_values(
        value: object,
        field: str,
        factory: Any,
    ) -> tuple[Any, ...]:
        if not isinstance(value, list):
            raise InvalidGeneratedResumeError(f"{field} must be an array")
        try:
            return tuple(factory(item) for item in value)
        except (TypeError, ValueError) as error:
            raise InvalidGeneratedResumeError(f"invalid {field}: {error}") from error

    def validate_against(
        self,
        knowledge: ResumeKnowledgeBase,
        *,
        candidate_skills: tuple[str, ...] = (),
    ) -> None:
        known_skills = {
            normalize_text(skill)
            for skill in (
                knowledge.all_skills
                + candidate_skills
                + tuple(
                    skill
                    for role in knowledge.roles
                    for skill in role.skills
                )
            )
        }
        unsupported_skills = [
            skill for skill in self.skills if normalize_text(skill) not in known_skills
        ]
        if unsupported_skills:
            raise InvalidGeneratedResumeError(
                "generated resume contains unsupported skills: "
                + ", ".join(unsupported_skills)
            )

        known_roles = {
            self._role_identity(role): role
            for role in knowledge.roles
        }
        for role in self.experience:
            source_role = known_roles.get(self._role_identity(role))
            if source_role is None:
                raise InvalidGeneratedResumeError(
                    "generated resume contains an unsupported experience entry: "
                    f"{role.title} at {role.company}"
                )
            known_responsibilities = {
                normalize_text(value) for value in source_role.evidence
            }
            unsupported = [
                value
                for value in role.responsibilities
                if normalize_text(value) not in known_responsibilities
            ]
            if unsupported:
                raise InvalidGeneratedResumeError(
                    "generated resume contains unsupported responsibilities: "
                    + ", ".join(unsupported)
                )

        self._validate_known_values(
            self.career_highlights,
            knowledge.achievements,
            field="career highlights",
        )
        self._validate_known_values(
            self.education,
            knowledge.education,
            field="education",
        )
        self._validate_known_values(
            self.certifications,
            knowledge.certifications,
            field="certifications",
        )

    @staticmethod
    def _validate_known_values(
        generated: tuple[Any, ...],
        known: tuple[Any, ...],
        *,
        field: str,
    ) -> None:
        known_values = set(known)
        unsupported = [value for value in generated if value not in known_values]
        if unsupported:
            raise InvalidGeneratedResumeError(
                f"generated resume contains unsupported {field}: "
                + ", ".join(str(value) for value in unsupported)
            )

    @staticmethod
    def _role_identity(role: GeneratedResumeRole | ResumeRole) -> tuple[object, ...]:
        return (
            normalize_text(role.company),
            normalize_text(role.title),
            normalize_text(role.location or ""),
            role.start_date,
            role.end_date,
        )
