"""SQLite persistence for application state transitions."""

from __future__ import annotations

import json

from database import Database
from models import Application, ApplicationStatus
from utils.dates import to_iso, utc_now


class ApplicationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, application: Application) -> None:
        payload = json.dumps(application.to_dict(), sort_keys=True)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO applications(
                    application_id, candidate_id, job_id, status, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(application_id) DO UPDATE SET
                    status = excluded.status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    application.application_id,
                    application.candidate_id,
                    application.job_id,
                    application.status.value,
                    payload,
                    to_iso(utc_now()),
                ),
            )

    def get(self, application_id: str) -> Application | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM applications WHERE application_id = ?",
                (application_id,),
            ).fetchone()
        return Application.from_dict(json.loads(row["payload_json"])) if row else None

    def list_by_status(self, status: ApplicationStatus) -> tuple[Application, ...]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM applications
                WHERE status = ?
                ORDER BY updated_at DESC
                """,
                (status.value,),
            ).fetchall()
        return tuple(Application.from_dict(json.loads(row["payload_json"])) for row in rows)
