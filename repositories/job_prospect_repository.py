"""MySQL persistence for the review-oriented job prospect projection."""

from __future__ import annotations

import json
from collections.abc import Sequence

from database import Database
from database.connection import MySQLCursor
from models import (
    DEFAULT_RESUME_CANDIDATE_THRESHOLD,
    DEFAULT_RESUME_GENERATION_MODEL,
    JobPosting,
    JobProspect,
    MatchResult,
)
from utils.dates import to_utc_naive


class JobProspectRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, prospect: JobProspect) -> None:
        with self._database.cursor() as cursor:
            self._save(cursor, prospect)

    @staticmethod
    def _save(cursor: MySQLCursor, prospect: JobProspect) -> None:
        cursor.execute(
            """
            INSERT INTO job_prospects(
                job_id, `match`, title, company, location, salary, source, url,
                posted_at, job_data, resume_generation_checked,
                resume_generation_candidate, resume_generation_model
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            ) AS incoming
            ON DUPLICATE KEY UPDATE
                `match` = COALESCE(incoming.`match`, job_prospects.`match`),
                title = incoming.title,
                company = incoming.company,
                location = incoming.location,
                salary = incoming.salary,
                source = incoming.source,
                url = incoming.url,
                posted_at = COALESCE(incoming.posted_at, job_prospects.posted_at),
                job_data = COALESCE(incoming.job_data, job_prospects.job_data),
                resume_generation_checked = incoming.resume_generation_checked,
                resume_generation_candidate = incoming.resume_generation_candidate,
                resume_generation_model = incoming.resume_generation_model,
                updated_at = UTC_TIMESTAMP(6)
            """,
            (
                prospect.job_id,
                prospect.match,
                prospect.title,
                prospect.company,
                prospect.location,
                prospect.salary,
                prospect.source,
                prospect.url,
                to_utc_naive(prospect.posted_at) if prospect.posted_at else None,
                None,
                prospect.resume_generation_checked,
                prospect.resume_generation_candidate,
                prospect.resume_generation_model,
            ),
        )

    def save_jobs(self, jobs: Sequence[JobPosting]) -> int:
        with self._database.cursor() as cursor:
            for job in jobs:
                prospect = JobProspect.from_job(job)
                cursor.execute(
                    """
                    INSERT INTO job_prospects(
                        job_id, `match`, title, company, location, salary, source,
                        url, posted_at, job_data, resume_generation_checked,
                        resume_generation_candidate, resume_generation_model
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    ) AS incoming
                    ON DUPLICATE KEY UPDATE
                        `match` = COALESCE(incoming.`match`, job_prospects.`match`),
                        title = incoming.title,
                        company = incoming.company,
                        location = incoming.location,
                        salary = incoming.salary,
                        source = incoming.source,
                        url = incoming.url,
                        posted_at = COALESCE(
                            incoming.posted_at,
                            job_prospects.posted_at
                        ),
                        job_data = CASE
                            WHEN incoming.posted_at IS NULL
                                 AND job_prospects.posted_at IS NOT NULL
                            THEN job_prospects.job_data
                            ELSE incoming.job_data
                        END,
                        updated_at = UTC_TIMESTAMP(6)
                    """,
                    (
                        prospect.job_id,
                        prospect.match,
                        prospect.title,
                        prospect.company,
                        prospect.location,
                        prospect.salary,
                        prospect.source,
                        prospect.url,
                        to_utc_naive(job.posted_at) if job.posted_at else None,
                        json.dumps(job.to_dict(), ensure_ascii=False, sort_keys=True),
                        prospect.resume_generation_checked,
                        prospect.resume_generation_candidate,
                        prospect.resume_generation_model,
                    ),
                )
        return len(jobs)

    def list_unchecked_resume_generation_jobs(
        self,
        *,
        limit: int = 15,
    ) -> tuple[JobPosting, ...]:
        if not 1 <= limit <= 15:
            raise ValueError("limit must be between 1 and 15")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_data
                FROM job_prospects
                WHERE resume_generation_checked = FALSE
                  AND job_data IS NOT NULL
                ORDER BY created_at, job_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        jobs: list[JobPosting] = []
        for row in rows:
            payload = row["job_data"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise TypeError("job_data must contain a JSON object")
            jobs.append(JobPosting.from_dict(payload))
        return tuple(jobs)

    def update_matches(
        self,
        matches: Sequence[MatchResult],
        *,
        resume_candidate_threshold: float = DEFAULT_RESUME_CANDIDATE_THRESHOLD,
        resume_generation_model: str = DEFAULT_RESUME_GENERATION_MODEL,
    ) -> int:
        if not 0 <= resume_candidate_threshold < 1:
            raise ValueError("resume candidate threshold must be at least 0 and less than 1")
        model = resume_generation_model.strip()
        if not model:
            raise ValueError("resume generation model must not be empty")
        with self._database.cursor() as cursor:
            for result in matches:
                is_resume_candidate = result.score > resume_candidate_threshold
                cursor.execute(
                    """
                    UPDATE job_prospects
                    SET `match` = %s,
                        resume_generation_checked = TRUE,
                        resume_generation_candidate = %s,
                        resume_generation_model = %s,
                        updated_at = UTC_TIMESTAMP(6)
                    WHERE job_id = %s
                    """,
                    (
                        result.score,
                        is_resume_candidate,
                        model if is_resume_candidate else None,
                        result.job_id,
                    ),
                )
        return len(matches)

    def list_resume_generation_candidates(
        self,
        *,
        limit: int = 100,
    ) -> tuple[JobProspect, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, `match`, title, company, location, salary, source,
                       url, posted_at, resume_generation_checked,
                       resume_generation_candidate, resume_generation_model,
                       created_at, updated_at
                FROM job_prospects
                WHERE resume_generation_checked = TRUE
                  AND resume_generation_candidate = TRUE
                ORDER BY `match` DESC, title, company
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(JobProspect.from_row(row) for row in rows)

    def matched_job_ids(self, job_ids: Sequence[str]) -> frozenset[str]:
        unique_ids = tuple(dict.fromkeys(job_id for job_id in job_ids if job_id))
        if not unique_ids:
            return frozenset()
        placeholders = ", ".join("%s" for _ in unique_ids)
        with self._database.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT job_id
                FROM job_prospects
                WHERE `match` IS NOT NULL
                  AND job_id IN ({placeholders})
                """,
                unique_ids,
            )
            rows = cursor.fetchall()
        return frozenset(str(row["job_id"]) for row in rows)

    def get(self, job_id: str) -> JobProspect | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, `match`, title, company, location, salary, source, url,
                       posted_at, resume_generation_checked,
                       resume_generation_candidate, resume_generation_model,
                       created_at, updated_at
                FROM job_prospects
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()
        return JobProspect.from_row(row) if row else None

    def get_job_posting(self, job_id: str) -> JobPosting | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, job_data
                FROM job_prospects
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()
        if not row or row.get("job_data") is None:
            return None
        payload = row["job_data"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise TypeError("job_data must contain a JSON object")
        return JobPosting.from_dict(payload)

    def list_ranked(self, *, limit: int = 100) -> tuple[JobProspect, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, `match`, title, company, location, salary, source, url,
                       posted_at, resume_generation_checked,
                       resume_generation_candidate, resume_generation_model,
                       created_at, updated_at
                FROM job_prospects
                ORDER BY (`match` IS NULL), `match` DESC, title, company
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(JobProspect.from_row(row) for row in rows)
