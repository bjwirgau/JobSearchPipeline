"""Crawler discovery cursor persistence tests."""

from __future__ import annotations

import unittest

from database import Database, MySQLConfig, initialize_schema
from models import CrawlDiscoveryCursor
from repositories import CrawlDiscoveryCursorRepository
from tests.mysql_fakes import FakeMySQLServer


class CrawlDiscoveryCursorRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = CrawlDiscoveryCursorRepository(database)

    def test_saves_and_advances_a_provider_scope(self) -> None:
        self.assertIsNone(
            self.repository.get(
                provider="internet_archive",
                scope="job-boards.greenhouse.io",
            )
        )
        self.repository.save(
            CrawlDiscoveryCursor(
                provider="internet_archive",
                scope="job-boards.greenhouse.io",
                next_page=1,
                page_count=4,
            )
        )
        self.repository.save(
            CrawlDiscoveryCursor(
                provider="internet_archive",
                scope="job-boards.greenhouse.io",
                next_page=2,
                page_count=4,
            )
        )

        state = self.repository.get(
            provider="internet_archive",
            scope="job-boards.greenhouse.io",
        )

        self.assertEqual(state.next_page, 2)
        self.assertEqual(state.page_count, 4)


if __name__ == "__main__":
    unittest.main()
