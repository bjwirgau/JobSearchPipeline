"""Transparent deterministic baseline for candidate/job scoring."""

from __future__ import annotations

import re

from models import CandidateProfile, JobPosting, MatchBreakdown, MatchResult
from utils.text import normalize_text, tokenize


YEARS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", re.IGNORECASE)


class MatchingAgent:
    def score(self, candidate: CandidateProfile, job: JobPosting) -> MatchResult:
        candidate_skills = {normalize_text(skill): skill for skill in candidate.skills}
        required_skills = {normalize_text(skill): skill for skill in job.skills}
        matched_keys = candidate_skills.keys() & required_skills.keys()
        missing_keys = required_skills.keys() - candidate_skills.keys()
        skill_score = len(matched_keys) / len(required_skills) if required_skills else 0.5

        desired_title_tokens = set(tokenize(" ".join(candidate.desired_titles)))
        job_title_tokens = set(tokenize(job.title))
        title_score = (
            len(desired_title_tokens & job_title_tokens) / len(job_title_tokens)
            if desired_title_tokens and job_title_tokens
            else 0.5
        )

        desired_locations = tuple(normalize_text(value) for value in candidate.desired_locations)
        if job.is_remote and candidate.remote_preference in {"remote", "flexible"}:
            location_score = 1.0
        elif desired_locations:
            location = normalize_text(job.location)
            location_score = 1.0 if any(value in location for value in desired_locations) else 0.0
        else:
            location_score = 0.5

        requirements_text = " ".join(job.requirements)
        years_match = YEARS_PATTERN.search(requirements_text)
        required_years = float(years_match.group(1)) if years_match else None
        experience_score = (
            min(candidate.years_experience / required_years, 1.0)
            if required_years and required_years > 0
            else 1.0
        )
        breakdown = MatchBreakdown(
            skills=skill_score,
            title=title_score,
            location=location_score,
            experience=experience_score,
        )
        total = (
            skill_score * 0.50
            + title_score * 0.25
            + location_score * 0.15
            + experience_score * 0.10
        )
        matched = tuple(required_skills[key] for key in sorted(matched_keys))
        missing = tuple(required_skills[key] for key in sorted(missing_keys))
        return MatchResult(
            candidate_id=candidate.candidate_id,
            job_id=job.job_id,
            score=round(total, 4),
            breakdown=breakdown,
            matched_skills=matched,
            missing_skills=missing,
            rationale=(
                f"Matched {len(matched)} of {len(required_skills)} identified skills; "
                f"title fit {title_score:.0%}, location fit {location_score:.0%}."
            ),
        )
