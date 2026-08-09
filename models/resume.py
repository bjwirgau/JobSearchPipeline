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


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field} must not be empty")
    return cleaned


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional resume fields must be strings or null")
    cleaned = value.strip()
    return cleaned or None


@dataclass(frozen=True, slots=True)
class ResumeAchievement:
    """A categorized, factual accomplishment from the candidate profile."""

    description: str
    category: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "description",
            _required_string(self.description, "resume achievement description"),
        )
        object.__setattr__(self, "category", _optional_string(self.category))

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "description": self.description,
        }

    @classmethod
    def from_value(cls, value: object) -> "ResumeAchievement":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(description=value)
        if not isinstance(value, Mapping):
            raise TypeError("resume achievements must be strings or objects")
        return cls(
            category=_optional_string(value.get("category")),
            description=_required_string(
                value.get("description"),
                "resume achievement description",
            ),
        )


@dataclass(frozen=True, slots=True)
class ResumeCertification:
    """A certification represented by the fields in the candidate JSON."""

    name: str
    issued: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _required_string(self.name, "resume certification name"),
        )
        object.__setattr__(self, "issued", _optional_string(self.issued))
        object.__setattr__(self, "status", _optional_string(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "issued": self.issued,
            "status": self.status,
        }

    @classmethod
    def from_value(cls, value: object) -> "ResumeCertification":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(name=value)
        if not isinstance(value, Mapping):
            raise TypeError("resume certifications must be strings or objects")
        return cls(
            name=_required_string(value.get("name"), "resume certification name"),
            issued=_optional_string(value.get("issued")),
            status=_optional_string(value.get("status")),
        )


@dataclass(frozen=True, slots=True)
class ResumeEducation:
    """An education record represented by the fields in the candidate JSON."""

    institution: str
    location: str | None = None
    degree: str | None = None
    field: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "institution",
            _required_string(self.institution, "resume education institution"),
        )
        for field_name in ("location", "degree", "field", "status"):
            object.__setattr__(
                self,
                field_name,
                _optional_string(getattr(self, field_name)),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "institution": self.institution,
            "location": self.location,
            "degree": self.degree,
            "field": self.field,
            "status": self.status,
        }

    @classmethod
    def from_value(cls, value: object) -> "ResumeEducation":
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(institution=value)
        if not isinstance(value, Mapping):
            raise TypeError("resume education entries must be strings or objects")
        return cls(
            institution=_required_string(
                value.get("institution"),
                "resume education institution",
            ),
            location=_optional_string(value.get("location")),
            degree=_optional_string(value.get("degree")),
            field=_optional_string(value.get("field")),
            status=_optional_string(value.get("status")),
        )


@dataclass(frozen=True, slots=True)
class ResumeRole:
    """Evidence from one role represented in the source resume."""

    company: str
    title: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    responsibilities: tuple[str, ...] = ()
    achievements: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("company", "title"):
            value = _required_string(
                getattr(self, field_name),
                f"resume role {field_name}",
            )
            object.__setattr__(self, field_name, value)
        for field_name in (
            "responsibilities",
            "achievements",
            "skills",
            "industries",
        ):
            object.__setattr__(self, field_name, _unique_strings(getattr(self, field_name)))
        object.__setattr__(self, "location", _optional_string(self.location))
        object.__setattr__(self, "start_date", _optional_string(self.start_date))
        object.__setattr__(self, "end_date", _optional_string(self.end_date))

    @property
    def evidence(self) -> tuple[str, ...]:
        """Return current responsibilities plus legacy role achievements."""

        return _unique_strings(self.responsibilities + self.achievements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "company": self.company,
            "title": self.title,
            "location": self.location,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "responsibilities": list(self.evidence),
            "skills": list(self.skills),
            "industries": list(self.industries),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResumeRole":
        return cls(
            company=_required_string(value.get("company"), "resume role company"),
            title=_required_string(value.get("title"), "resume role title"),
            location=_optional_string(value.get("location")),
            start_date=value.get("start_date"),
            end_date=value.get("end_date"),
            responsibilities=tuple(value.get("responsibilities", ())),
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
    achievements: tuple[ResumeAchievement, ...] = ()
    certifications: tuple[ResumeCertification, ...] = ()
    education: tuple[ResumeEducation, ...] = ()
    schema_version: int = 1
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        candidate_id = self.candidate_id.strip()
        if not candidate_id:
            raise ValueError("candidate_id must not be empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be greater than zero")
        object.__setattr__(self, "candidate_id", candidate_id)

        for field_name in ("skills", "industries"):
            object.__setattr__(self, field_name, _unique_strings(getattr(self, field_name)))
        object.__setattr__(self, "roles", tuple(self.roles))
        object.__setattr__(
            self,
            "achievements",
            tuple(ResumeAchievement.from_value(value) for value in self.achievements),
        )
        object.__setattr__(
            self,
            "certifications",
            tuple(ResumeCertification.from_value(value) for value in self.certifications),
        )
        object.__setattr__(
            self,
            "education",
            tuple(ResumeEducation.from_value(value) for value in self.education),
        )

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
            "achievements": [value.to_dict() for value in self.achievements],
            "certifications": [value.to_dict() for value in self.certifications],
            "education": [value.to_dict() for value in self.education],
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
