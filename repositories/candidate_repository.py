"""MySQL persistence for candidate profiles."""

from __future__ import annotations

import json

from database import Database
from models import CandidateProfile
from utils.dates import to_utc_naive, utc_now


class CandidateRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, candidate: CandidateProfile) -> None:
        payload = json.dumps(candidate.to_dict(), sort_keys=True)
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO candidates(candidate_id, full_name, email, payload_json, updated_at)
                VALUES (%s, %s, %s, %s, %s) AS incoming
                ON DUPLICATE KEY UPDATE
                    full_name = incoming.full_name,
                    email = incoming.email,
                    payload_json = incoming.payload_json,
                    updated_at = incoming.updated_at
                """,
                (
                    candidate.candidate_id,
                    candidate.full_name,
                    candidate.email,
                    payload,
                    to_utc_naive(utc_now()),
                ),
            )

    def get(self, candidate_id: str) -> CandidateProfile | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM candidates WHERE candidate_id = %s",
                (candidate_id,),
            )
            row = cursor.fetchone()
        return CandidateProfile.from_dict(json.loads(row["payload_json"])) if row else None
