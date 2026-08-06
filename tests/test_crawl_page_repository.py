"""Page-level crawl history repository tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from database import Database, MySQLConfig, initialize_schema
from models import CrawlPage, CrawlPageType, CrawlStatus
from repositories import CrawlPageRepository
from tests.mysql_fakes import FakeMySQLServer


class CrawlPageRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = CrawlPageRepository(database)
        self.now = datetime(2026, 8, 6, 12, tzinfo=timezone.utc)
        self.url = "https://job-boards.greenhouse.io/example"

    def test_blocks_a_page_only_until_its_revisit_time(self) -> None:
        page = CrawlPage.from_attempt(
            page_url=self.url,
            source="greenhouse",
            page_type=CrawlPageType.COMPANY_BOARD,
            crawl_status=CrawlStatus.FAILED,
            crawled_at=self.now,
            revisit_after=timedelta(hours=24),
            last_error="board not found",
        )

        self.repository.save_all((page,))

        self.assertEqual(
            self.repository.blocked_urls(
                source="greenhouse",
                page_type=CrawlPageType.COMPANY_BOARD,
                as_of=self.now + timedelta(hours=23),
            ),
            frozenset({self.url}),
        )
        self.assertEqual(
            self.repository.blocked_urls(
                source="greenhouse",
                page_type=CrawlPageType.COMPANY_BOARD,
                as_of=self.now + timedelta(hours=24),
            ),
            frozenset(),
        )

    def test_updates_outcome_without_replacing_creation_time(self) -> None:
        failed = CrawlPage.from_attempt(
            page_url=self.url,
            source="greenhouse",
            page_type=CrawlPageType.COMPANY_BOARD,
            crawl_status=CrawlStatus.FAILED,
            crawled_at=self.now,
            revisit_after=timedelta(hours=1),
            last_error="temporary failure",
        )
        self.repository.save_all((failed,))
        created = self.repository.get(self.url)

        succeeded = CrawlPage.from_attempt(
            page_url=self.url,
            source="greenhouse",
            page_type=CrawlPageType.COMPANY_BOARD,
            crawl_status=CrawlStatus.SUCCESS,
            crawled_at=self.now + timedelta(hours=2),
            revisit_after=timedelta(days=7),
        )
        self.repository.save_all((succeeded,))
        updated = self.repository.get(self.url)

        self.assertEqual(updated.crawl_status, CrawlStatus.SUCCESS)
        self.assertIsNone(updated.last_error)
        self.assertEqual(updated.created_at, created.created_at)
        self.assertGreaterEqual(updated.updated_at, created.updated_at)


if __name__ == "__main__":
    unittest.main()
