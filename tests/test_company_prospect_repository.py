"""MySQL company-prospect repository tests."""

from __future__ import annotations

import unittest

from database import Database, MySQLConfig, initialize_schema
from models import CompanyProspect
from repositories import CompanyProspectRepository
from tests.mysql_fakes import FakeMySQLServer


class CompanyProspectRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = CompanyProspectRepository(database)

    def test_saves_and_updates_a_company_without_replacing_created_at(self) -> None:
        prospect = CompanyProspect.from_board(
            company_name="Example Company",
            board_token="Example",
            company_url="https://job-boards.greenhouse.io/example",
        )

        self.repository.save(prospect)
        created = self.repository.get(prospect.company_id)

        self.assertIsNotNone(created)
        self.assertEqual(created.company_name, "Example Company")
        self.assertEqual(created.board_token, "example")
        self.assertIsNotNone(created.created_at)
        self.assertEqual(created.created_at, created.updated_at)
        self.assertEqual(
            self.repository.known_company_urls(),
            frozenset({prospect.company_url}),
        )

        renamed = CompanyProspect.from_board(
            company_name="Renamed Company",
            board_token="example",
            company_url=prospect.company_url,
        )
        self.repository.save(renamed)
        updated = self.repository.get(prospect.company_id)

        self.assertEqual(updated.company_name, "Renamed Company")
        self.assertEqual(updated.created_at, created.created_at)
        self.assertGreaterEqual(updated.updated_at, created.updated_at)
        self.assertEqual(self.repository.list_all(), (updated,))
        self.assertEqual(self.repository.list_all(limit=1), (updated,))

    def test_list_all_rejects_a_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.repository.list_all(limit=0)

    def test_rejects_non_greenhouse_company_urls(self) -> None:
        with self.assertRaisesRegex(ValueError, "canonical Greenhouse"):
            CompanyProspect.from_board(
                company_name="Example Company",
                board_token="example",
                company_url="https://example.com/jobs",
            )


if __name__ == "__main__":
    unittest.main()
