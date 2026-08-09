"""Validated content selected by the LLM for a tailored resume."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .resume import ResumeKnowledgeBase
from utils.text import normalize_text


class InvalidGeneratedResumeError(ValueError):
    pass


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
    start_date: str | None
    end_date: str | None
    achievements: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedResumeRole":
        return cls(
            company=_string(value.get("company"), "experience company"),
            title=_string(value.get("title"), "experience title"),
            start_date=_optional_string(
                value.get("start_date"),
                "experience start_date",
            ),
            end_date=_optional_string(value.get("end_date"), "experience end_date"),
            achievements=_strings(
                value.get("achievements"),
                "experience achievements",
            ),
        )


@dataclass(frozen=True, slots=True)
class GeneratedResumeContent:
    professional_summary: str
    skills: tuple[str, ...]
    experience: tuple[GeneratedResumeRole, ...]
    career_highlights: tuple[str, ...]
    education: tuple[str, ...]
    certifications: tuple[str, ...]

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
            skills=_strings(value.get("skills"), "skills"),
            experience=tuple(experience),
            career_highlights=_strings(
                value.get("career_highlights"),
                "career_highlights",
            ),
            education=_strings(value.get("education"), "education"),
            certifications=_strings(
                value.get("certifications"),
                "certifications",
            ),
        )

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
            (
                normalize_text(role.company),
                normalize_text(role.title),
                role.start_date,
                role.end_date,
            )
            for role in knowledge.roles
        }
        for role in self.experience:
            identity = (
                normalize_text(role.company),
                normalize_text(role.title),
                role.start_date,
                role.end_date,
            )
            if identity not in known_roles:
                raise InvalidGeneratedResumeError(
                    "generated resume contains an unsupported experience entry: "
                    f"{role.title} at {role.company}"
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
        generated: tuple[str, ...],
        known: tuple[str, ...],
        *,
        field: str,
    ) -> None:
        known_values = {normalize_text(value) for value in known}
        unsupported = [
            value for value in generated if normalize_text(value) not in known_values
        ]
        if unsupported:
            raise InvalidGeneratedResumeError(
                f"generated resume contains unsupported {field}: "
                + ", ".join(unsupported)
            )
