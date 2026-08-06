"""MySQL persistence for companies discovered on Greenhouse."""

from __future__ import annotations

from collections.abc import Sequence

from database import Database
from database.connection import MySQLCursor
from models import CompanyProspect


class CompanyProspectRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save(self, prospect: CompanyProspect) -> None:
        with self._database.cursor() as cursor:
            self._save(cursor, prospect)

    def save_all(self, prospects: Sequence[CompanyProspect]) -> int:
        with self._database.cursor() as cursor:
            for prospect in prospects:
                self._save(cursor, prospect)
        return len(prospects)

    @staticmethod
    def _save(cursor: MySQLCursor, prospect: CompanyProspect) -> None:
        cursor.execute(
            """
            INSERT INTO company_prospects(
                company_id, company_name, board_token, company_url
            )
            VALUES (%s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                company_name = incoming.company_name,
                board_token = incoming.board_token,
                company_url = incoming.company_url,
                updated_at = UTC_TIMESTAMP(6)
            """,
            (
                prospect.company_id,
                prospect.company_name,
                prospect.board_token,
                prospect.company_url,
            ),
        )

    def get(self, company_id: str) -> CompanyProspect | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT company_id, company_name, board_token, company_url,
                       created_at, updated_at
                FROM company_prospects
                WHERE company_id = %s
                """,
                (company_id,),
            )
            row = cursor.fetchone()
        return CompanyProspect.from_row(row) if row else None

    def known_company_urls(self) -> frozenset[str]:
        with self._database.cursor() as cursor:
            cursor.execute("SELECT company_url FROM company_prospects")
            rows = cursor.fetchall()
        return frozenset(str(row["company_url"]) for row in rows)

    def list_all(self, *, limit: int = 100) -> tuple[CompanyProspect, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT company_id, company_name, board_token, company_url,
                       created_at, updated_at
                FROM company_prospects
                ORDER BY company_name, board_token
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(CompanyProspect.from_row(row) for row in rows)
