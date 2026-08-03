"""Candidate-to-job matching results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from utils.dates import to_iso, utc_now


@dataclass(frozen=True, slots=True)
class MatchBreakdown:
    skills: float
    title: float
    location: float
    experience: float
    industry: float = 0.5

    def __post_init__(self) -> None:
        for field_name in ("skills", "title", "location", "experience", "industry"):
            score = getattr(self, field_name)
            if not 0.0 <= score <= 1.0:
                raise ValueError(f"{field_name} score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class MatchResult:
    candidate_id: str
    job_id: str
    score: float
    breakdown: MatchBreakdown
    matched_skills: tuple[str, ...] = ()
    missing_skills: tuple[str, ...] = ()
    skill_years: Mapping[str, float] = field(default_factory=dict)
    rationale: str = ""
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError("score must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "score": self.score,
            "breakdown": {
                "skills": self.breakdown.skills,
                "title": self.breakdown.title,
                "location": self.breakdown.location,
                "experience": self.breakdown.experience,
                "industry": self.breakdown.industry,
            },
            "matched_skills": list(self.matched_skills),
            "missing_skills": list(self.missing_skills),
            "skill_years": dict(self.skill_years),
            "rationale": self.rationale,
            "created_at": to_iso(self.created_at),
        }
