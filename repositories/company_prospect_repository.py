"""MySQL persistence for companies discovered on Greenhouse."""

from __future__ import annotations

from collections.abc import Sequence

from database import Database
from database.connection import MySQLCursor
from models import CompanyProspect
from utils.dates import to_utc_naive, utc_now


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
                       last_job_search_at, created_at, updated_at
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

    def list_all(self, *, limit: int | None = None) -> tuple[CompanyProspect, ...]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than zero")
        query = """
                SELECT company_id, company_name, board_token, company_url,
                       last_job_search_at, created_at, updated_at
                FROM company_prospects
                WHERE company_url LIKE 'https://job-boards.greenhouse.io/%'
                ORDER BY company_name, board_token
                """
        parameters: tuple[object, ...] = ()
        if limit is not None:
            query += " LIMIT %s"
            parameters = (limit,)
        with self._database.cursor() as cursor:
            cursor.execute(query, parameters)
            rows = cursor.fetchall()
        return tuple(CompanyProspect.from_row(row) for row in rows)

    def reserve_for_job_search(self, *, limit: int) -> tuple[CompanyProspect, ...]:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        selected_at = to_utc_naive(utc_now())
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT company_id, company_name, board_token, company_url,
                       last_job_search_at, created_at, updated_at
                FROM company_prospects
                WHERE company_url LIKE 'https://job-boards.greenhouse.io/%'
                ORDER BY (last_job_search_at IS NOT NULL), last_job_search_at,
                         company_name, board_token
                LIMIT %s
                FOR UPDATE
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            if rows:
                company_ids = tuple(str(row["company_id"]) for row in rows)
                placeholders = ", ".join("%s" for _ in company_ids)
                cursor.execute(
                    f"""
                    UPDATE company_prospects
                    SET last_job_search_at = %s
                    WHERE company_id IN ({placeholders})
                    """,
                    (selected_at, *company_ids),
                )
        return tuple(CompanyProspect.from_row(row) for row in rows)
