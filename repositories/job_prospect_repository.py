"""MySQL persistence for the review-oriented job prospect projection."""

from __future__ import annotations

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
                job_id, `match`, title, company, location, salary, source, url
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                `match` = COALESCE(incoming.`match`, job_prospects.`match`),
                title = incoming.title,
                company = incoming.company,
                location = incoming.location,
                salary = incoming.salary,
                source = incoming.source,
                url = incoming.url,
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
            ),
        )

    def save_jobs(self, jobs: Sequence[JobPosting]) -> int:
        with self._database.cursor() as cursor:
            for job in jobs:
                self._save(cursor, JobProspect.from_job(job))
        return len(jobs)

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
