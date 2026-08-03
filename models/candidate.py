"""Candidate profile shared by matching and application workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    candidate_id: str
    full_name: str
    email: str
    location: str = ""
    summary: str = ""
    skills: tuple[str, ...] = ()
    years_experience: float = 0.0
    desired_titles: tuple[str, ...] = ()
    desired_locations: tuple[str, ...] = ()
    remote_preference: str = "flexible"
    resume_path: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("candidate_id", "full_name", "email"):
            value = getattr(self, field_name).strip()
            if not value:
                raise ValueError(f"{field_name} must not be empty")
            object.__setattr__(self, field_name, value)
        if self.years_experience < 0:
            raise ValueError("years_experience must not be negative")
        for field_name in ("skills", "desired_titles", "desired_locations"):
            object.__setattr__(
                self,
                field_name,
                tuple(value.strip() for value in getattr(self, field_name) if value.strip()),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "full_name": self.full_name,
            "email": self.email,
            "location": self.location,
            "summary": self.summary,
            "skills": list(self.skills),
            "years_experience": self.years_experience,
            "desired_titles": list(self.desired_titles),
            "desired_locations": list(self.desired_locations),
            "remote_preference": self.remote_preference,
            "resume_path": self.resume_path,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CandidateProfile":
        return cls(
            candidate_id=str(value["candidate_id"]),
            full_name=str(value["full_name"]),
            email=str(value["email"]),
            location=str(value.get("location", "")),
            summary=str(value.get("summary", "")),
            skills=tuple(value.get("skills", ())),
            years_experience=float(value.get("years_experience", 0)),
            desired_titles=tuple(value.get("desired_titles", ())),
            desired_locations=tuple(value.get("desired_locations", ())),
            remote_preference=str(value.get("remote_preference", "flexible")),
            resume_path=value.get("resume_path"),
        )
