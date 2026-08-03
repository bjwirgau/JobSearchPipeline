"""SQLite persistence for candidate profiles."""

from __future__ import annotations

import json

from database import Database
from models import CandidateProfile
from utils.dates import to_iso, utc_now


class CandidateRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, candidate: CandidateProfile) -> None:
        payload = json.dumps(candidate.to_dict(), sort_keys=True)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO candidates(candidate_id, full_name, email, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    email = excluded.email,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate.candidate_id,
                    candidate.full_name,
                    candidate.email,
                    payload,
                    to_iso(utc_now()),
                ),
            )

    def get(self, candidate_id: str) -> CandidateProfile | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return CandidateProfile.from_dict(json.loads(row["payload_json"])) if row else None
