"""MySQL job-prospect repository tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from database import Database, MySQLConfig, initialize_schema
from models import JobPosting, JobProspect, MatchBreakdown, MatchResult
from repositories import JobProspectRepository
from tests.mysql_fakes import FakeMySQLServer


class JobProspectRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = JobProspectRepository(database)

    def test_saves_updates_scores_and_ranks_job_prospects(self) -> None:
        job = JobPosting(
            source="sample",
            external_id="job-1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1?utm_source=test",
            location="Denver, CO",
            salary_min=140000,
            salary_max=180000,
            salary_currency="USD",
        )
        self.assertEqual(self.repository.save_jobs((job,)), 1)
        self.assertEqual(
            self.repository.get(job.job_id),
            JobProspect.from_job(job),
        )

        updated_job = replace(job, title="Senior Data Engineer")
        self.repository.save_jobs((updated_job,))
        match = MatchResult(
            candidate_id="candidate-1",
            job_id=job.job_id,
            score=0.875,
            breakdown=MatchBreakdown(
                skills=0.9,
                title=0.8,
                location=1.0,
                experience=0.8,
            ),
        )
        self.assertEqual(self.repository.update_matches((match,)), 1)

        expected = JobProspect.from_job(updated_job, match=0.875)
        self.assertEqual(self.repository.get(job.job_id), expected)
        self.assertEqual(self.repository.list_ranked(), (expected,))

        rescored = replace(expected, match=0.9)
        self.repository.save(rescored)
        self.repository.save_jobs((updated_job,))
        self.assertEqual(self.repository.get(job.job_id), rescored)

    def test_rejects_invalid_match_score(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            JobProspect(
                job_id="job-1",
                match=1.1,
                title="Data Engineer",
                company="Example",
                location="Remote",
                salary="Not provided",
                source="sample",
                url="https://example.com/jobs/1",
            )


if __name__ == "__main__":
    unittest.main()
