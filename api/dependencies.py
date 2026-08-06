"""Repository dependencies exposed to API route handlers."""

from __future__ import annotations

from dataclasses import dataclass

from repositories import JobProspectRepository


@dataclass(frozen=True, slots=True)
class ApiDependencies:
    job_prospects: JobProspectRepository
