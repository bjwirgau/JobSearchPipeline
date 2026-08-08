"""Search skeleton tests using the local in-memory source."""

from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any, Mapping

from agents import (
    MatchingAgent,
    ParserAgent,
    SearchAgent,
    SearchDisabledError,
    SearchQueryBuilder,
)
from database import Database, MySQLConfig, initialize_schema
from models import CandidateProfile, JobPosting, JobProspect, SearchCriteria
from repositories import JobProspectRepository
from services import InMemoryJobSource, LoggingNotificationService
from tests.mysql_fakes import FakeMySQLServer
from workflows import JobMatchingWorkflow, JobSearchWorkflow


MATCH_PROMPT = "{candidate_profile}\n{resume_knowledge}\n{job_posting}"


class StaticMatchLLM:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str) -> str:
        raise AssertionError("matching must use structured output")

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.prompts.append(prompt)
        return {
            "score": 0.88,
            "breakdown": {
                "skills": 1.0,
                "title": 1.0,
                "location": 1.0,
                "experience": 0.7,
                "industry": 0.5,
            },
            "matched_skills": ["Python"],
            "missing_skills": [],
            "rationale": "Strong evidence for this role.",
        }


class SearchAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = JobProspectRepository(database)

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
        stored = self.repository.get(job.job_id)
        self.assertEqual(
            replace(stored, created_at=None, updated_at=None),
            JobProspect.from_job(job),
        )
        self.assertIsNotNone(stored.created_at)
        self.assertIsNotNone(stored.updated_at)

    async def test_search_stores_jobs_for_the_separate_matching_workflow(self) -> None:
        job = JobPosting(
            source="fixture",
            external_id="matched-job",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/matched",
            location="Denver, CO",
            skills=("Python",),
        )
        search_agent = SearchAgent(
            sources=(InMemoryJobSource("fixture", (job,)),),
            repository=self.repository,
            enabled=True,
        )
        llm = StaticMatchLLM()
        search_workflow = JobSearchWorkflow(
            search_agent=search_agent,
            parser_agent=ParserAgent(),
        )
        matching_workflow = JobMatchingWorkflow(
            repository=self.repository,
            parser_agent=ParserAgent(),
            matching_agent=MatchingAgent(
                llm=llm,
                prompt_template=MATCH_PROMPT,
            ),
            notifications=LoggingNotificationService(),
        )

        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            skills=("Python",),
            desired_titles=("Data Engineer",),
            desired_locations=("Denver, CO",),
        )
        criteria = SearchCriteria(
            job_titles=("Data Engineer",),
            locations=("Denver, CO",),
        )
        search_result = await search_workflow.run(criteria)

        prospect = self.repository.get(job.job_id)
        self.assertIsNotNone(prospect)
        self.assertIsNone(prospect.match)
        self.assertEqual(search_result.jobs, (job,))
        self.assertEqual(len(llm.prompts), 0)

        match_result = await matching_workflow.run(candidate)

        prospect = self.repository.get(job.job_id)
        self.assertAlmostEqual(prospect.match, match_result.matches[0].score)
        self.assertEqual(len(llm.prompts), 1)

        repeated = await matching_workflow.run(candidate)

        self.assertEqual(repeated.jobs, ())
        self.assertEqual(repeated.matches, ())
        self.assertEqual(len(llm.prompts), 1)

    async def test_workflow_caps_gemini_requests_at_fifteen_per_run(self) -> None:
        jobs = tuple(
            JobPosting(
                source="fixture",
                external_id=f"job-{index}",
                title="Data Engineer",
                company=f"Example {index}",
                url=f"https://example.com/jobs/{index}",
                location="Remote",
                skills=("Python",),
            )
            for index in range(20)
        )
        search_agent = SearchAgent(
            sources=(InMemoryJobSource("fixture", jobs),),
            repository=self.repository,
            enabled=True,
        )
        llm = StaticMatchLLM()
        search_workflow = JobSearchWorkflow(
            search_agent=search_agent,
            parser_agent=ParserAgent(),
        )
        matching_workflow = JobMatchingWorkflow(
            repository=self.repository,
            parser_agent=ParserAgent(),
            matching_agent=MatchingAgent(
                llm=llm,
                prompt_template=MATCH_PROMPT,
            ),
            notifications=LoggingNotificationService(),
        )
        candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Example Candidate",
            email="candidate@example.com",
            skills=("Python",),
            desired_titles=("Data Engineer",),
        )

        search_result = await search_workflow.run(
            SearchCriteria(job_titles=("Data Engineer",), results_per_query=20),
        )
        result = await matching_workflow.run(candidate)

        self.assertEqual(len(search_result.jobs), 20)
        self.assertEqual(len(result.jobs), 15)
        self.assertEqual(len(result.matches), 15)
        self.assertEqual(len(llm.prompts), 15)
        self.assertEqual(
            sum(self.repository.get(job.job_id).match is not None for job in jobs),
            15,
        )

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
