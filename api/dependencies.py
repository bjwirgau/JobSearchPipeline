"""Repository dependencies exposed to API route handlers."""

from __future__ import annotations

from dataclasses import dataclass

from repositories import ApplicationRepository, CandidateRepository, JobRepository


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    jobs: JobRepository
    applications: ApplicationRepository
    candidates: CandidateRepository
