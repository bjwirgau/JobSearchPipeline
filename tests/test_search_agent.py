"""Search skeleton tests using the local in-memory source."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agents import SearchAgent, SearchDisabledError
from database import Database, initialize_schema
from models import JobPosting, SearchCriteria
from repositories import JobRepository
from services import InMemoryJobSource


class SearchAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        database = Database(Path(self._temporary_directory.name) / "test.sqlite3")
        initialize_schema(database)
        self.repository = JobRepository(database)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    async def test_search_is_disabled_by_default(self) -> None:
        agent = SearchAgent(sources=(), repository=self.repository)
        with self.assertRaises(SearchDisabledError):
            await agent.search(SearchCriteria(job_titles=("Data Engineer",)))

    async def test_in_memory_source_runs_without_network_access(self) -> None:
        job = JobPosting(
            source="fixture",
            external_id="job-1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            location="Denver, CO",
        )
        agent = SearchAgent(
            sources=(InMemoryJobSource("fixture", (job,)),),
            repository=self.repository,
            enabled=True,
        )

        result = await agent.search(
            SearchCriteria(
                job_titles=("Data Engineer",),
                locations=("Denver, CO",),
            )
        )

        self.assertEqual(result.jobs, (job,))
        self.assertEqual(result.stored_count, 1)
        self.assertEqual(self.repository.get(job.job_id), job)


if __name__ == "__main__":
    unittest.main()
