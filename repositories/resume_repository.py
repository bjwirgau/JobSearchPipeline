"""SQLite persistence for structured resume knowledge."""

from __future__ import annotations

import json

from database import Database
from models import ResumeKnowledgeBase
from utils.dates import to_iso


class ResumeKnowledgeRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, knowledge: ResumeKnowledgeBase) -> None:
        payload = json.dumps(knowledge.to_dict(), sort_keys=True)
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO resume_knowledge(
                    candidate_id, schema_version, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    knowledge.candidate_id,
                    knowledge.schema_version,
                    payload,
                    to_iso(knowledge.updated_at),
                ),
            )

    def get(self, candidate_id: str) -> ResumeKnowledgeBase | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM resume_knowledge WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return ResumeKnowledgeBase.from_dict(json.loads(row["payload_json"])) if row else None

    def delete(self, candidate_id: str) -> bool:
        with self._database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM resume_knowledge WHERE candidate_id = ?",
                (candidate_id,),
            )
        return cursor.rowcount > 0
