"""MySQL job-prospect repository tests."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone

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
            posted_at=datetime(2026, 8, 1, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(self.repository.save_jobs((job,)), 1)
        self.assertEqual(
            self.repository.list_unchecked_resume_generation_jobs(),
            (job,),
        )
        self.assertEqual(self.repository.matched_job_ids((job.job_id,)), frozenset())
        created = self.repository.get(job.job_id)
        self.assertIsNotNone(created)
        self.assertEqual(
            replace(created, created_at=None, updated_at=None),
            JobProspect.from_job(job),
        )
        self.assertIsNotNone(created.created_at)
        self.assertEqual(created.created_at, created.updated_at)
        self.assertEqual(created.posted_at, job.posted_at)

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
        self.assertEqual(
            self.repository.list_unchecked_resume_generation_jobs(),
            (),
        )
        self.assertEqual(
            self.repository.matched_job_ids((job.job_id, "unknown-job")),
            frozenset({job.job_id}),
        )

        expected = JobProspect.from_job(
            updated_job,
            match=0.875,
            resume_generation_checked=True,
            resume_generation_candidate=True,
            resume_generation_model="gpt-5.4",
        )
        updated = self.repository.get(job.job_id)
        self.assertEqual(
            replace(updated, created_at=None, updated_at=None),
            expected,
        )
        self.assertEqual(updated.created_at, created.created_at)
        self.assertGreaterEqual(updated.updated_at, created.updated_at)
        self.assertEqual(self.repository.list_ranked(), (updated,))
        self.assertEqual(
            self.repository.list_resume_generation_candidates(),
            (updated,),
        )

        rescored = replace(expected, match=0.9)
        self.repository.save(rescored)
        self.repository.save_jobs((updated_job,))
        final = self.repository.get(job.job_id)
        self.assertEqual(
            replace(final, created_at=None, updated_at=None),
            rescored,
        )
        self.assertEqual(final.created_at, created.created_at)
        self.assertGreaterEqual(final.updated_at, updated.updated_at)

    def test_match_must_exceed_threshold_to_become_resume_candidate(self) -> None:
        jobs = tuple(
            JobPosting(
                source="sample",
                external_id=f"job-{index}",
                title=f"Data Engineer {index}",
                company="Example",
                url=f"https://example.com/jobs/{index}",
            )
            for index in range(2)
        )
        self.repository.save_jobs(jobs)
        matches = tuple(
            MatchResult(
                candidate_id="candidate-1",
                job_id=job.job_id,
                score=score,
                breakdown=MatchBreakdown(
                    skills=score,
                    title=score,
                    location=score,
                    experience=score,
                ),
            )
            for job, score in zip(jobs, (0.85, 0.86))
        )

        self.repository.update_matches(matches)

        threshold_match = self.repository.get(jobs[0].job_id)
        qualifying_match = self.repository.get(jobs[1].job_id)
        self.assertTrue(threshold_match.resume_generation_checked)
        self.assertFalse(threshold_match.resume_generation_candidate)
        self.assertIsNone(threshold_match.resume_generation_model)
        self.assertTrue(qualifying_match.resume_generation_checked)
        self.assertTrue(qualifying_match.resume_generation_candidate)
        self.assertEqual(qualifying_match.resume_generation_model, "gpt-5.4")
        self.assertEqual(
            self.repository.list_resume_generation_candidates(),
            (qualifying_match,),
        )

    def test_preserves_scraped_posting_date_when_later_enrichment_fails(self) -> None:
        posted_at = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
        scraped = JobPosting(
            source="greenhouse",
            external_id="job-1",
            title="Data Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            description="Scraped description",
            posted_at=posted_at,
        )
        self.repository.save_jobs((scraped,))

        self.repository.save_jobs(
            (replace(scraped, description="API fallback", posted_at=None),)
        )

        stored = self.repository.get(scraped.job_id)
        unchecked = self.repository.list_unchecked_resume_generation_jobs()
        self.assertEqual(stored.posted_at, posted_at)
        self.assertEqual(unchecked[0].posted_at, posted_at)
        self.assertEqual(unchecked[0].description, "Scraped description")

    def test_legacy_match_remains_eligible_until_explicitly_checked(self) -> None:
        job = JobPosting(
            source="sample",
            external_id="legacy-job",
            title="Software Engineer",
            company="Example",
            url="https://example.com/jobs/legacy",
        )
        self.repository.save_jobs((job,))
        self.repository.save(JobProspect.from_job(job, match=0.8))

        stored = self.repository.get(job.job_id)

        self.assertAlmostEqual(stored.match, 0.8)
        self.assertFalse(stored.resume_generation_checked)
        self.assertEqual(
            self.repository.list_unchecked_resume_generation_jobs(),
            (job,),
        )

    def test_serializes_database_timestamps(self) -> None:
        prospect = JobProspect(
            job_id="job-1",
            match=None,
            title="Data Engineer",
            company="Example",
            location="Remote",
            salary="Not provided",
            source="sample",
            url="https://example.com/jobs/1",
        )
        self.repository.save(prospect)

        stored = self.repository.get(prospect.job_id)
        payload = stored.to_dict()

        self.assertTrue(str(payload["created_at"]).endswith("+00:00"))
        self.assertTrue(str(payload["updated_at"]).endswith("+00:00"))

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

        with self.assertRaisesRegex(ValueError, "between 1 and 15"):
            self.repository.list_unchecked_resume_generation_jobs(limit=16)


if __name__ == "__main__":
    unittest.main()
