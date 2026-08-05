"""MySQL persistence and retrieval for normalized jobs."""

from __future__ import annotations

import json
from collections.abc import Sequence

from database import Database
from database.connection import MySQLCursor
from models import JobPosting
from utils.dates import to_utc_naive, utc_now


class JobRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, job: JobPosting) -> None:
        with self._database.cursor() as cursor:
            self._save(cursor, job)

    @staticmethod
    def _save(cursor: MySQLCursor, job: JobPosting) -> None:
        payload = json.dumps(job.to_dict(), sort_keys=True)
        cursor.execute(
            """
            INSERT INTO jobs(
                job_id, source, external_id, deduplication_key,
                title, company, payload_json, discovered_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                title = incoming.title,
                company = incoming.company,
                deduplication_key = incoming.deduplication_key,
                payload_json = incoming.payload_json,
                updated_at = incoming.updated_at
            """,
            (
                job.job_id,
                job.source,
                job.external_id,
                job.deduplication_key,
                job.title,
                job.company,
                payload,
                to_utc_naive(job.discovered_at),
                to_utc_naive(utc_now()),
            ),
        )

    def save_many(self, jobs: Sequence[JobPosting]) -> int:
        with self._database.cursor() as cursor:
            for job in jobs:
                self._save(cursor, job)
        return len(jobs)

    def get(self, job_id: str) -> JobPosting | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM jobs WHERE job_id = %s",
                (job_id,),
            )
            row = cursor.fetchone()
        return JobPosting.from_dict(json.loads(row["payload_json"])) if row else None

    def list_recent(self, *, limit: int = 100) -> tuple[JobPosting, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload_json FROM jobs
                ORDER BY discovered_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(JobPosting.from_dict(json.loads(row["payload_json"])) for row in rows)
