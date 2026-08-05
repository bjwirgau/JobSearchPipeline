"""MySQL application-repository tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from database import Database, MySQLConfig, initialize_schema
from models import Application, ApplicationStatus, CandidateProfile, JobPosting
from repositories import ApplicationRepository, CandidateRepository, JobRepository
from tests.mysql_fakes import FakeMySQLServer


class ApplicationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        CandidateRepository(database).save(
            CandidateProfile(
                candidate_id="candidate-1",
                full_name="Example Candidate",
                email="candidate@example.com",
            )
        )
        JobRepository(database).save(
            JobPosting(
                source="sample",
                external_id="job-1",
                title="Data Engineer",
                company="Example",
                url="https://example.com/jobs/1",
            )
        )
        self.repository = ApplicationRepository(database)

    def test_saves_updates_reads_and_filters_an_application(self) -> None:
        application = Application(
            application_id="application-1",
            candidate_id="candidate-1",
            job_id=JobPosting(
                source="sample",
                external_id="job-1",
                title="Data Engineer",
                company="Example",
                url="https://example.com/jobs/1",
            ).job_id,
        )
        self.repository.save(application)

        self.assertEqual(self.repository.get(application.application_id), application)

        updated = replace(application, status=ApplicationStatus.REVIEW_REQUIRED)
        self.repository.save(updated)

        self.assertEqual(self.repository.get(application.application_id), updated)
        self.assertEqual(
            self.repository.list_by_status(ApplicationStatus.REVIEW_REQUIRED),
            (updated,),
        )
        self.assertEqual(self.repository.list_by_status(ApplicationStatus.DRAFT), ())


if __name__ == "__main__":
    unittest.main()
