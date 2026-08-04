"""SQLite job-repository tests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from database import Database, initialize_schema
from models import JobPosting
from repositories import JobRepository


class JobRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        database = Database(Path(self._temporary_directory.name) / "test.sqlite3")
        initialize_schema(database)
        self.repository = JobRepository(database)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_saves_reads_and_updates_a_job(self) -> None:
        job = JobPosting(
            source="sample",
            external_id="job-1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1?utm_source=test",
            description="Original description",
            is_remote=True,
            remote_country_codes=("US",),
        )
        self.repository.save(job)

        loaded = self.repository.get(job.job_id)
        self.assertEqual(loaded, job)

        updated = replace(job, description="Updated description")
        self.repository.save(updated)

        self.assertEqual(self.repository.get(job.job_id), updated)
        self.assertEqual(self.repository.list_recent(), (updated,))


if __name__ == "__main__":
    unittest.main()
