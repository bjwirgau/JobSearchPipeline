"""MySQL persistence for structured resume knowledge."""

from __future__ import annotations

import json

from database import Database
from models import ResumeKnowledgeBase
from utils.dates import to_utc_naive


class ResumeKnowledgeRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, knowledge: ResumeKnowledgeBase) -> None:
        payload = json.dumps(knowledge.to_dict(), sort_keys=True)
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO resume_knowledge(
                    candidate_id, schema_version, payload_json, updated_at
                )
                VALUES (%s, %s, %s, %s) AS incoming
                ON DUPLICATE KEY UPDATE
                    schema_version = incoming.schema_version,
                    payload_json = incoming.payload_json,
                    updated_at = incoming.updated_at
                """,
                (
                    knowledge.candidate_id,
                    knowledge.schema_version,
                    payload,
                    to_utc_naive(knowledge.updated_at),
                ),
            )

    def get(self, candidate_id: str) -> ResumeKnowledgeBase | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM resume_knowledge WHERE candidate_id = %s",
                (candidate_id,),
            )
            row = cursor.fetchone()
        return ResumeKnowledgeBase.from_dict(json.loads(row["payload_json"])) if row else None

    def delete(self, candidate_id: str) -> bool:
        with self._database.cursor() as cursor:
            cursor.execute(
                "DELETE FROM resume_knowledge WHERE candidate_id = %s",
                (candidate_id,),
            )
            return cursor.rowcount > 0
