"""Shared source-adapter filtering helpers."""

from __future__ import annotations

from models import JobPosting, SearchQuery
from utils.text import normalize_text, tokenize
from utils.countries import remote_country_is_eligible


def job_matches_query(job: JobPosting, query: SearchQuery) -> bool:
    if query.remote_only and job.is_remote is not True:
        return False
    if (
        query.remote_country
        and job.is_remote is True
        and not remote_country_is_eligible(
            query.remote_country,
            job.remote_country_codes,
            job.location,
        )
    ):
        return False
    if query.location and job.is_remote is not True:
        location = normalize_text(job.location)
        if normalize_text(query.location) not in location:
            return False
    if query.title:
        desired_title = set(tokenize(query.title))
        actual_title = set(tokenize(job.title))
        if desired_title and len(desired_title & actual_title) / len(desired_title) < 0.6:
            return False
    return True
