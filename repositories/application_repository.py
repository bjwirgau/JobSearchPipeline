"""MySQL persistence for application state transitions."""

from __future__ import annotations

import json

from database import Database
from models import Application, ApplicationStatus
from utils.dates import to_utc_naive, utc_now


class ApplicationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, application: Application) -> None:
        payload = json.dumps(application.to_dict(), sort_keys=True)
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO applications(
                    application_id, candidate_id, job_id, status, payload_json, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s) AS incoming
                ON DUPLICATE KEY UPDATE
                    status = incoming.status,
                    payload_json = incoming.payload_json,
                    updated_at = incoming.updated_at
                """,
                (
                    application.application_id,
                    application.candidate_id,
                    application.job_id,
                    application.status.value,
                    payload,
                    to_utc_naive(utc_now()),
                ),
            )

    def get(self, application_id: str) -> Application | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM applications WHERE application_id = %s",
                (application_id,),
            )
            row = cursor.fetchone()
        return Application.from_dict(json.loads(row["payload_json"])) if row else None

    def list_by_status(self, status: ApplicationStatus) -> tuple[Application, ...]:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload_json FROM applications
                WHERE status = %s
                ORDER BY updated_at DESC
                """,
                (status.value,),
            )
            rows = cursor.fetchall()
        return tuple(Application.from_dict(json.loads(row["payload_json"])) for row in rows)
