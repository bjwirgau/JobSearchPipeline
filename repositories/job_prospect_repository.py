"""MySQL persistence for the review-oriented job prospect projection."""

from __future__ import annotations

import json
from collections.abc import Sequence

from database import Database
from database.connection import MySQLCursor
from models import JobPosting, JobProspect, MatchResult


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
                job_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                `match` = COALESCE(incoming.`match`, job_prospects.`match`),
                title = incoming.title,
                company = incoming.company,
                location = incoming.location,
                salary = incoming.salary,
                source = incoming.source,
                url = incoming.url,
                job_data = COALESCE(incoming.job_data, job_prospects.job_data),
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
                None,
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
                        url, job_data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) AS incoming
                    ON DUPLICATE KEY UPDATE
                        `match` = COALESCE(incoming.`match`, job_prospects.`match`),
                        title = incoming.title,
                        company = incoming.company,
                        location = incoming.location,
                        salary = incoming.salary,
                        source = incoming.source,
                        url = incoming.url,
                        job_data = incoming.job_data,
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
                        json.dumps(job.to_dict(), ensure_ascii=False, sort_keys=True),
                    ),
                )
        return len(jobs)

    def list_unmatched_jobs(self, *, limit: int = 15) -> tuple[JobPosting, ...]:
        if not 1 <= limit <= 15:
            raise ValueError("limit must be between 1 and 15")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_data
                FROM job_prospects
                WHERE `match` IS NULL
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

    def update_matches(self, matches: Sequence[MatchResult]) -> int:
        with self._database.cursor() as cursor:
            for result in matches:
                cursor.execute(
                    """
                    UPDATE job_prospects
                    SET `match` = %s,
                        updated_at = UTC_TIMESTAMP(6)
                    WHERE job_id = %s
                    """,
                    (result.score, result.job_id),
                )
        return len(matches)

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
                       created_at, updated_at
                FROM job_prospects
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cursor.fetchone()
        return JobProspect.from_row(row) if row else None

    def list_ranked(self, *, limit: int = 100) -> tuple[JobProspect, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT job_id, `match`, title, company, location, salary, source, url,
                       created_at, updated_at
                FROM job_prospects
                ORDER BY (`match` IS NULL), `match` DESC, title, company
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(JobProspect.from_row(row) for row in rows)
