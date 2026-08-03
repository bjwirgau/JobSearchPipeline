"""Structured, validated resume knowledge for matching and tailoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from utils.dates import from_iso, to_iso, utc_now
from utils.text import normalize_text


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for raw_value in values:
        value = str(raw_value).strip()
        if value:
            unique.setdefault(normalize_text(value), value)
    return tuple(unique.values())


@dataclass(frozen=True, slots=True)
class ResumeRole:
    """Evidence from one role represented in the source resume."""

    company: str
    title: str
    start_date: str | None = None
    end_date: str | None = None
    achievements: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("company", "title"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"resume role {field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        for field_name in ("achievements", "skills", "industries"):
            object.__setattr__(self, field_name, _unique_strings(getattr(self, field_name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "title": self.title,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "achievements": list(self.achievements),
            "skills": list(self.skills),
            "industries": list(self.industries),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResumeRole":
        return cls(
            company=str(value["company"]),
            title=str(value["title"]),
            start_date=value.get("start_date"),
            end_date=value.get("end_date"),
            achievements=tuple(value.get("achievements", ())),
            skills=tuple(value.get("skills", ())),
            industries=tuple(value.get("industries", ())),
        )


@dataclass(frozen=True, slots=True)
class ResumeKnowledgeBase:
    """Machine-readable facts derived from a candidate's resume."""

    candidate_id: str
    skills: tuple[str, ...] = ()
    years: Mapping[str, float] = field(default_factory=dict)
    industries: tuple[str, ...] = ()
    roles: tuple[ResumeRole, ...] = ()
    achievements: tuple[str, ...] = ()
    certifications: tuple[str, ...] = ()
    education: tuple[str, ...] = ()
    schema_version: int = 1
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        candidate_id = self.candidate_id.strip()
        if not candidate_id:
            raise ValueError("candidate_id must not be empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be greater than zero")
        object.__setattr__(self, "candidate_id", candidate_id)

        for field_name in (
            "skills",
            "industries",
            "achievements",
            "certifications",
            "education",
        ):
            object.__setattr__(self, field_name, _unique_strings(getattr(self, field_name)))
        object.__setattr__(self, "roles", tuple(self.roles))

        normalized_years: dict[str, float] = {}
        display_names: dict[str, str] = {}
        for raw_skill, raw_years in self.years.items():
            skill = str(raw_skill).strip()
            if not skill:
                raise ValueError("skill-year names must not be empty")
            if isinstance(raw_years, bool) or not isinstance(raw_years, (int, float)):
                raise TypeError(f"years for {skill} must be numeric")
            years = float(raw_years)
            if years < 0 or years > 100:
                raise ValueError(f"years for {skill} must be between 0 and 100")
            key = normalize_text(skill)
            display_names.setdefault(key, skill)
            normalized_years[key] = max(years, normalized_years.get(key, 0.0))
        object.__setattr__(
            self,
            "years",
            MappingProxyType(
                {display_names[key]: normalized_years[key] for key in display_names}
            ),
        )

    @property
    def all_skills(self) -> tuple[str, ...]:
        return _unique_strings(self.skills + tuple(self.years))

    def years_for(self, skill: str) -> float | None:
        target = normalize_text(skill)
        for known_skill, years in self.years.items():
            if normalize_text(known_skill) == target:
                return years
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "skills": list(self.skills),
            "years": dict(self.years),
            "industries": list(self.industries),
            "roles": [role.to_dict() for role in self.roles],
            "achievements": list(self.achievements),
            "certifications": list(self.certifications),
            "education": list(self.education),
            "updated_at": to_iso(self.updated_at),
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        candidate_id: str | None = None,
    ) -> "ResumeKnowledgeBase":
        resolved_candidate_id = value.get("candidate_id") or candidate_id
        if not resolved_candidate_id:
            raise ValueError("resume knowledge requires a candidate_id")
        raw_years = value.get("years", {})
        if not isinstance(raw_years, Mapping):
            raise TypeError("resume knowledge years must be an object")
        raw_roles = value.get("roles", ())
        return cls(
            schema_version=int(value.get("schema_version", 1)),
            candidate_id=str(resolved_candidate_id),
            skills=tuple(value.get("skills", ())),
            years=raw_years,
            industries=tuple(value.get("industries", ())),
            roles=tuple(ResumeRole.from_dict(role) for role in raw_roles),
            achievements=tuple(value.get("achievements", ())),
            certifications=tuple(value.get("certifications", ())),
            education=tuple(value.get("education", ())),
            updated_at=from_iso(value.get("updated_at")) or utc_now(),
        )
