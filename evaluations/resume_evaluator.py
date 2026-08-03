"""Honest keyword-coverage check for reviewable resume drafts."""

from __future__ import annotations

from dataclasses import dataclass

from utils.text import normalize_text


@dataclass(frozen=True, slots=True)
class ResumeEvaluation:
    coverage: float
    present: tuple[str, ...]
    missing: tuple[str, ...]


class ResumeEvaluator:
    def evaluate(self, resume_text: str, expected_skills: tuple[str, ...]) -> ResumeEvaluation:
        normalized = normalize_text(resume_text)
        present = tuple(skill for skill in expected_skills if normalize_text(skill) in normalized)
        missing = tuple(skill for skill in expected_skills if skill not in present)
        coverage = len(present) / len(expected_skills) if expected_skills else 1.0
        return ResumeEvaluation(coverage, present, missing)
