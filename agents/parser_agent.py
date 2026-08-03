"""Deterministic Phase 1 parser for structured job details."""

from __future__ import annotations

from dataclasses import replace

from models import JobPosting
from utils.text import normalize_text


DEFAULT_SKILL_VOCABULARY = (
    "Python",
    "SQL",
    "JavaScript",
    "TypeScript",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Terraform",
    "dbt",
    "Spark",
)


class ParserAgent:
    def __init__(self, skill_vocabulary: tuple[str, ...] = DEFAULT_SKILL_VOCABULARY) -> None:
        self._skill_vocabulary = skill_vocabulary

    def parse(self, job: JobPosting) -> JobPosting:
        responsibilities, requirements = self._extract_sections(job.description)
        normalized_description = normalize_text(job.description)
        skills = tuple(
            skill
            for skill in self._skill_vocabulary
            if normalize_text(skill) in normalized_description
        )
        return replace(
            job,
            skills=job.skills or skills,
            responsibilities=job.responsibilities or responsibilities,
            requirements=job.requirements or requirements,
        )

    @staticmethod
    def _extract_sections(description: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        buckets: dict[str, list[str]] = {"responsibilities": [], "requirements": []}
        current: str | None = None
        for raw_line in description.splitlines():
            line = raw_line.strip()
            heading = normalize_text(line.rstrip(":"))
            if heading in {"responsibilities", "what you will do", "the role"}:
                current = "responsibilities"
                continue
            if heading in {"requirements", "qualifications", "what you bring"}:
                current = "requirements"
                continue
            value = line.lstrip("-*• ").strip()
            if current and value:
                buckets[current].append(value)
        return tuple(buckets["responsibilities"]), tuple(buckets["requirements"])
