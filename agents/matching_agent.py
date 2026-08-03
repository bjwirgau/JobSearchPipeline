"""Transparent deterministic baseline for candidate/job scoring."""

from __future__ import annotations

import re

from models import (
    CandidateProfile,
    JobPosting,
    MatchBreakdown,
    MatchResult,
    ResumeKnowledgeBase,
)
from utils.text import normalize_text, tokenize


YEARS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)", re.IGNORECASE)


class MatchingAgent:
    def score(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        resume_knowledge: ResumeKnowledgeBase | None = None,
    ) -> MatchResult:
        candidate_skills = {normalize_text(skill): skill for skill in candidate.skills}
        if resume_knowledge:
            for skill in resume_knowledge.all_skills:
                candidate_skills.setdefault(normalize_text(skill), skill)
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
        experience_years = candidate.years_experience
        if resume_knowledge and required_years:
            relevant_years = tuple(
                years
                for key in matched_keys
                if (years := resume_knowledge.years_for(required_skills[key])) is not None
            )
            if relevant_years:
                experience_years = max(relevant_years)
        experience_score = (
            min(experience_years / required_years, 1.0)
            if required_years and required_years > 0
            else 1.0
        )

        required_industries = {normalize_text(value): value for value in job.industries}
        candidate_industries = {
            normalize_text(value): value
            for value in (resume_knowledge.industries if resume_knowledge else ())
        }
        industry_score = (
            len(required_industries.keys() & candidate_industries.keys())
            / len(required_industries)
            if required_industries
            else 0.5
        )
        breakdown = MatchBreakdown(
            skills=skill_score,
            title=title_score,
            location=location_score,
            experience=experience_score,
            industry=industry_score,
        )
        base_total = (
            skill_score * 0.50
            + title_score * 0.25
            + location_score * 0.15
            + experience_score * 0.10
        )
        total = base_total * 0.90 + industry_score * 0.10 if required_industries else base_total
        matched = tuple(required_skills[key] for key in sorted(matched_keys))
        missing = tuple(required_skills[key] for key in sorted(missing_keys))
        skill_years = {
            required_skills[key]: years
            for key in sorted(matched_keys)
            if resume_knowledge
            and (years := resume_knowledge.years_for(required_skills[key])) is not None
        }
        industry_detail = (
            f", industry fit {industry_score:.0%}" if required_industries else ""
        )
        return MatchResult(
            candidate_id=candidate.candidate_id,
            job_id=job.job_id,
            score=round(total, 4),
            breakdown=breakdown,
            matched_skills=matched,
            missing_skills=missing,
            skill_years=skill_years,
            rationale=(
                f"Matched {len(matched)} of {len(required_skills)} identified skills; "
                f"title fit {title_score:.0%}, location fit {location_score:.0%}"
                f"{industry_detail}."
            ),
        )
