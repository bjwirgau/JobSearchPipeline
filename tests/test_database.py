"""MySQL connection and transaction behavior tests."""

from __future__ import annotations

import unittest

from database import Database, MySQLConfig, initialize_schema
from tests.mysql_fakes import FakeMySQLServer


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeMySQLServer()
        self.config = MySQLConfig(
            host="mysql.internal",
            port=3307,
            database="job_agent_test",
            user="test_user",
            password="secret",
            connection_timeout=4,
        )
        self.database = Database(
            self.config,
            connect_factory=self.server.connect,
        )

    def test_schema_initialization_uses_configured_mysql_connection(self) -> None:
        initialize_schema(self.database)

        self.assertEqual(
            self.server.connect_calls[0],
            {
                "host": "mysql.internal",
                "port": 3307,
                "database": "job_agent_test",
                "user": "test_user",
                "password": "secret",
                "connection_timeout": 4,
                "charset": "utf8mb4",
                "use_unicode": True,
                "autocommit": False,
                "time_zone": "+00:00",
            },
        )
        self.assertTrue(self.server.connections[0].committed)
        self.assertTrue(self.server.connections[0].closed)
        self.assertIn("job_prospects", self.server.tables)
        self.assertIn("company_prospects", self.server.tables)
        self.assertIn("crawl_pages", self.server.tables)
        self.assertIn("crawl_discovery_cursors", self.server.tables)
        self.assertNotIn("applications", self.server.tables)
        self.assertNotIn("candidates", self.server.tables)
        self.assertNotIn("jobs", self.server.tables)
        self.assertFalse(self.server.resume_candidate_foreign_key)
        self.assertEqual(
            set(self.server.tables["schema_migrations"]),
            {2, 13},
        )
        self.assertIn("created_at", self.server.job_prospect_columns)
        self.assertIn("updated_at", self.server.job_prospect_columns)
        self.assertIn("job_data", self.server.job_prospect_columns)
        self.assertIn("posted_at", self.server.job_prospect_columns)
        self.assertIn(
            "resume_generation_checked",
            self.server.job_prospect_columns,
        )
        self.assertIn(
            "resume_generation_candidate",
            self.server.job_prospect_columns,
        )
        self.assertIn("resume_generation_model", self.server.job_prospect_columns)
        self.assertIn("resume_file_name", self.server.job_prospect_columns)
        self.assertIn("last_job_search_at", self.server.company_prospect_columns)

    def test_version_three_schema_adds_job_prospect_timestamps(self) -> None:
        self.server.tables = {
            "schema_migrations": {
                3: {"version": 3, "applied_at": None},
            },
            "resume_knowledge": {},
            "job_prospects": {
                "existing-job": {
                    "job_id": "existing-job",
                    "match": None,
                    "title": "Data Engineer",
                    "company": "Example",
                    "location": "Remote",
                    "salary": "Not provided",
                    "source": "fixture",
                    "url": "https://example.com/jobs/1",
                }
            },
            "workflow_runs": {},
        }
        self.server.job_prospect_columns = {
            "job_id",
            "match",
            "title",
            "company",
            "location",
            "salary",
            "source",
            "url",
        }
        self.server.resume_candidate_foreign_key = False

        initialize_schema(self.database)

        self.assertEqual(
            set(self.server.tables["schema_migrations"]),
            {3, 13},
        )
        self.assertIn("created_at", self.server.job_prospect_columns)
        self.assertIn("updated_at", self.server.job_prospect_columns)
        self.assertIn("job_data", self.server.job_prospect_columns)
        self.assertIn("posted_at", self.server.job_prospect_columns)
        migrated = self.server.tables["job_prospects"]["existing-job"]
        self.assertIsNotNone(migrated["created_at"])
        self.assertIsNotNone(migrated["updated_at"])
        self.assertIsNone(migrated["job_data"])
        self.assertIsNone(migrated["posted_at"])
        self.assertFalse(migrated["resume_generation_checked"])
        self.assertFalse(migrated["resume_generation_candidate"])
        self.assertIsNone(migrated["resume_generation_model"])
        self.assertIsNone(migrated["resume_file_name"])

    def test_version_eight_schema_backfills_resume_candidates(self) -> None:
        self.server.tables = {
            "schema_migrations": {
                8: {"version": 8, "applied_at": None},
            },
            "resume_knowledge": {},
            "job_prospects": {
                "qualifying": {
                    "job_id": "qualifying",
                    "match": 0.86,
                    "title": "Data Engineer",
                    "company": "Example",
                    "location": "Remote",
                    "salary": "Not provided",
                    "source": "fixture",
                    "url": "https://example.com/jobs/1",
                    "job_data": None,
                    "created_at": None,
                    "updated_at": None,
                },
                "threshold": {
                    "job_id": "threshold",
                    "match": 0.85,
                    "title": "Software Engineer",
                    "company": "Example",
                    "location": "Remote",
                    "salary": "Not provided",
                    "source": "fixture",
                    "url": "https://example.com/jobs/2",
                    "job_data": None,
                    "created_at": None,
                    "updated_at": None,
                },
            },
            "company_prospects": {},
            "crawl_pages": {},
            "workflow_runs": {},
        }
        self.server.job_prospect_columns = {
            "job_id",
            "match",
            "title",
            "company",
            "location",
            "salary",
            "source",
            "url",
            "job_data",
            "created_at",
            "updated_at",
        }
        self.server.company_prospect_columns = {
            "company_id",
            "company_name",
            "board_token",
            "company_url",
            "last_job_search_at",
            "created_at",
            "updated_at",
        }
        self.server.resume_candidate_foreign_key = False

        initialize_schema(self.database)

        qualifying = self.server.tables["job_prospects"]["qualifying"]
        threshold = self.server.tables["job_prospects"]["threshold"]
        self.assertTrue(qualifying["resume_generation_candidate"])
        self.assertFalse(qualifying["resume_generation_checked"])
        self.assertEqual(qualifying["resume_generation_model"], "gpt-5.4")
        self.assertFalse(threshold["resume_generation_candidate"])
        self.assertFalse(threshold["resume_generation_checked"])
        self.assertIsNone(threshold["resume_generation_model"])
        self.assertIn("posted_at", self.server.job_prospect_columns)
        self.assertIn("resume_file_name", self.server.job_prospect_columns)

    def test_version_twelve_schema_adds_resume_file_name(self) -> None:
        self.server.tables = {
            "schema_migrations": {
                12: {"version": 12, "applied_at": None},
            },
            "resume_knowledge": {},
            "job_prospects": {
                "existing-job": {
                    "job_id": "existing-job",
                    "match": 0.9,
                    "title": "Data Engineer",
                    "company": "Example",
                    "location": "Remote",
                    "salary": "Not provided",
                    "source": "fixture",
                    "url": "https://example.com/jobs/1",
                    "posted_at": None,
                    "job_data": {},
                    "resume_generation_checked": True,
                    "resume_generation_candidate": True,
                    "resume_generation_model": "gpt-5.4",
                    "created_at": None,
                    "updated_at": None,
                }
            },
            "company_prospects": {},
            "crawl_pages": {},
            "crawl_discovery_cursors": {},
            "workflow_runs": {},
        }
        self.server.job_prospect_columns = {
            "job_id",
            "match",
            "title",
            "company",
            "location",
            "salary",
            "source",
            "url",
            "posted_at",
            "job_data",
            "resume_generation_checked",
            "resume_generation_candidate",
            "resume_generation_model",
            "created_at",
            "updated_at",
        }
        self.server.company_prospect_columns = {
            "company_id",
            "company_name",
            "board_token",
            "company_url",
            "last_job_search_at",
            "created_at",
            "updated_at",
        }
        self.server.resume_candidate_foreign_key = False

        initialize_schema(self.database)

        self.assertEqual(set(self.server.tables["schema_migrations"]), {12, 13})
        self.assertIn("resume_file_name", self.server.job_prospect_columns)
        self.assertIsNone(
            self.server.tables["job_prospects"]["existing-job"]["resume_file_name"]
        )

    def test_failed_transaction_rolls_back_and_closes(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "stop transaction"):
            with self.database.cursor() as cursor:
                self.assertTrue(cursor.dictionary)
                raise RuntimeError("stop transaction")

        connection = self.server.connections[-1]
        self.assertTrue(connection.rolled_back)
        self.assertFalse(connection.committed)
        self.assertTrue(connection.closed)

    def test_password_is_not_in_config_representation(self) -> None:
        self.assertNotIn("secret", repr(self.config))


if __name__ == "__main__":
    unittest.main()
