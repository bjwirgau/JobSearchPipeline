"""SQLite persistence and retrieval for normalized jobs."""

from __future__ import annotations

import json
from collections.abc import Sequence

from database import Database
from models import JobPosting
from utils.dates import to_iso, utc_now


class JobRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, job: JobPosting) -> None:
        payload = json.dumps(job.to_dict(), sort_keys=True)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, source, external_id, deduplication_key,
                    title, company, payload_json, discovered_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    deduplication_key = excluded.deduplication_key,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    job.job_id,
                    job.source,
                    job.external_id,
                    job.deduplication_key,
                    job.title,
                    job.company,
                    payload,
                    to_iso(job.discovered_at),
                    to_iso(utc_now()),
                ),
            )

    def save_many(self, jobs: Sequence[JobPosting]) -> int:
        for job in jobs:
            self.save(job)
        return len(jobs)

    def get(self, job_id: str) -> JobPosting | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return JobPosting.from_dict(json.loads(row["payload_json"])) if row else None

    def list_recent(self, *, limit: int = 100) -> tuple[JobPosting, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM jobs
                ORDER BY discovered_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(JobPosting.from_dict(json.loads(row["payload_json"])) for row in rows)
