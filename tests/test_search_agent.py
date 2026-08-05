"""Search skeleton tests using the local in-memory source."""

from __future__ import annotations

import unittest

from agents import SearchAgent, SearchDisabledError, SearchQueryBuilder
from database import Database, MySQLConfig, initialize_schema
from models import JobPosting, SearchCriteria
from repositories import JobRepository
from services import InMemoryJobSource
from tests.mysql_fakes import FakeMySQLServer


class SearchAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = JobRepository(database)

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

    async def test_query_builder_preserves_discovery_criteria(self) -> None:
        query = SearchQueryBuilder().build(
            SearchCriteria(
                job_titles=("Software Engineer",),
                skills=("PHP", "React", "AWS"),
                required_keywords=("PHP", "AWS"),
                locations=("Denver, CO",),
                location_radius_miles=50,
                remote_country="US",
                employment_types=("full-time",),
                minimum_salary=140000,
                excluded_keywords=("intern",),
                max_age_days=14,
            )
        )[0]

        self.assertEqual(query.text, "Software Engineer")
        self.assertEqual(query.skills, ("PHP", "React", "AWS"))
        self.assertEqual(query.required_keywords, ("PHP", "AWS"))
        self.assertEqual(query.location, "Denver, CO")
        self.assertEqual(query.location_radius_miles, 50)
        self.assertEqual(query.remote_country, "us")
        self.assertEqual(query.employment_types, ("full-time",))
        self.assertEqual(query.minimum_salary, 140000)
        self.assertEqual(query.excluded_keywords, ("intern",))
        self.assertEqual(query.max_age_days, 14)

    async def test_query_builder_omits_locations_for_remote_searches(self) -> None:
        queries = SearchQueryBuilder().build(
            SearchCriteria(
                job_titles=("Software Engineer", "Backend Engineer"),
                locations=("Denver, CO", "Austin, TX"),
                location_radius_miles=50,
                remote_only=True,
                remote_country="us",
            )
        )

        self.assertEqual(len(queries), 2)
        self.assertTrue(all(query.remote_only for query in queries))
        self.assertTrue(all(query.location is None for query in queries))
        self.assertTrue(
            all(query.location_radius_miles is None for query in queries)
        )

    async def test_required_keywords_are_hard_filters_after_source_search(self) -> None:
        jobs = (
            JobPosting(
                source="fixture",
                external_id="matching",
                title="Software Engineer",
                company="Example",
                url="https://example.com/jobs/matching",
                description="Build services with Python and AWS.",
            ),
            JobPosting(
                source="fixture",
                external_id="missing",
                title="Software Engineer",
                company="Example Two",
                url="https://example.com/jobs/missing",
                description="Build services with Python.",
            ),
        )
        agent = SearchAgent(
            sources=(InMemoryJobSource("fixture", jobs),),
            repository=self.repository,
            enabled=True,
        )

        result = await agent.search(
            SearchCriteria(
                job_titles=("Software Engineer",),
                required_keywords=("Python", "AWS"),
            )
        )

        self.assertEqual(result.jobs, (jobs[0],))

    async def test_remote_country_accepts_matching_and_worldwide_jobs(self) -> None:
        jobs = (
            JobPosting(
                source="fixture",
                external_id="us-remote",
                title="Software Engineer",
                company="US Remote",
                url="https://example.com/jobs/us",
                location="Remote - United States",
                is_remote=True,
                remote_country_codes=("us",),
            ),
            JobPosting(
                source="fixture",
                external_id="worldwide",
                title="Software Engineer",
                company="Worldwide",
                url="https://example.com/jobs/worldwide",
                location="Worldwide",
                is_remote=True,
                remote_country_codes=("*",),
            ),
            JobPosting(
                source="fixture",
                external_id="canada",
                title="Software Engineer",
                company="Canada Remote",
                url="https://example.com/jobs/canada",
                location="Remote - Canada",
                is_remote=True,
                remote_country_codes=("ca",),
            ),
            JobPosting(
                source="fixture",
                external_id="unknown",
                title="Software Engineer",
                company="Unknown Remote",
                url="https://example.com/jobs/unknown",
                location="Remote",
                is_remote=True,
            ),
            JobPosting(
                source="fixture",
                external_id="onsite",
                title="Software Engineer",
                company="Onsite",
                url="https://example.com/jobs/onsite",
                location="Denver, CO",
                is_remote=False,
            ),
        )
        agent = SearchAgent(
            sources=(InMemoryJobSource("fixture", jobs),),
            repository=self.repository,
            enabled=True,
        )

        result = await agent.search(
            SearchCriteria(
                job_titles=("Software Engineer",),
                remote_country="us",
            )
        )

        self.assertEqual(result.jobs, (jobs[0], jobs[1], jobs[4]))


if __name__ == "__main__":
    unittest.main()
