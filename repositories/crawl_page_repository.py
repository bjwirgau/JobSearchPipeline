"""MySQL persistence for page-level crawler history."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from database import Database
from database.connection import MySQLCursor
from models import CrawlPage, CrawlPageType
from utils.dates import to_utc_naive


class CrawlPageRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def save_all(self, pages: Sequence[CrawlPage]) -> int:
        with self._database.cursor() as cursor:
            for page in pages:
                self._save(cursor, page)
        return len(pages)

    @staticmethod
    def _save(cursor: MySQLCursor, page: CrawlPage) -> None:
        cursor.execute(
            """
            INSERT INTO crawl_pages(
                page_url, source, page_type, crawl_status,
                last_crawled_at, next_crawl_at, last_error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s) AS incoming
            ON DUPLICATE KEY UPDATE
                source = incoming.source,
                page_type = incoming.page_type,
                crawl_status = incoming.crawl_status,
                last_crawled_at = incoming.last_crawled_at,
                next_crawl_at = incoming.next_crawl_at,
                last_error = incoming.last_error,
                updated_at = UTC_TIMESTAMP(6)
            """,
            (
                page.page_url,
                page.source,
                page.page_type.value,
                page.crawl_status.value,
                to_utc_naive(page.last_crawled_at),
                to_utc_naive(page.next_crawl_at),
                page.last_error,
            ),
        )

    def blocked_urls(
        self,
        *,
        source: str,
        page_type: CrawlPageType,
        as_of: datetime,
    ) -> frozenset[str]:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT page_url
                FROM crawl_pages
                WHERE source = %s
                  AND page_type = %s
                  AND next_crawl_at > %s
                """,
                (
                    source.casefold(),
                    page_type.value,
                    to_utc_naive(as_of),
                ),
            )
            rows = cursor.fetchall()
        return frozenset(str(row["page_url"]) for row in rows)

    def get(self, page_url: str) -> CrawlPage | None:
        with self._database.cursor() as cursor:
            cursor.execute(
                """
                SELECT page_url, source, page_type, crawl_status,
                       last_crawled_at, next_crawl_at, last_error,
                       created_at, updated_at
                FROM crawl_pages
                WHERE page_url = %s
                """,
                (page_url,),
            )
            row = cursor.fetchone()
        return CrawlPage.from_row(row) if row else None
