"""MySQL persistence for crawler index pagination."""

from __future__ import annotations

from database import Database
from database.connection import MySQLCursor
from models import CrawlDiscoveryCursor


class CrawlDiscoveryCursorRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def get(self, *, provider: str, scope: str) -> CrawlDiscoveryCursor | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT provider, scope_key, next_page, page_count
                FROM crawl_discovery_cursors
                WHERE provider = %s AND scope_key = %s
                """,
                (provider.casefold(), scope),
            )
            row = cursor.fetchone()
        return CrawlDiscoveryCursor.from_row(row) if row else None

    def save(self, cursor_state: CrawlDiscoveryCursor) -> None:
        with self._database.cursor() as cursor:
            self._save(cursor, cursor_state)

    @staticmethod
    def _save(cursor: MySQLCursor, state: CrawlDiscoveryCursor) -> None:
        cursor.execute(
            """
            INSERT INTO crawl_discovery_cursors(
                provider, scope_key, next_page, page_count
            )
            VALUES (%s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                next_page = incoming.next_page,
                page_count = incoming.page_count,
                updated_at = UTC_TIMESTAMP(6)
            """,
            (
                state.provider.casefold(),
                state.scope,
                state.next_page,
                state.page_count,
            ),
        )
