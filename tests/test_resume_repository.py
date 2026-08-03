"""SQLite resume-knowledge repository tests."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from database import Database, initialize_schema
from models import CandidateProfile, ResumeKnowledgeBase
from repositories import CandidateRepository, ResumeKnowledgeRepository


class ResumeKnowledgeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        database = Database(Path(self._temporary_directory.name) / "test.sqlite3")
        initialize_schema(database)
        CandidateRepository(database).save(
            CandidateProfile(
                candidate_id="candidate-1",
                full_name="Example Candidate",
                email="candidate@example.com",
            )
        )
        self.repository = ResumeKnowledgeRepository(database)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_saves_updates_reads_and_deletes_knowledge(self) -> None:
        knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("PHP",),
            years={"PHP": 10},
            industries=("Ecommerce",),
        )
        self.repository.save(knowledge)
        self.assertEqual(self.repository.get("candidate-1"), knowledge)

        updated = replace(knowledge, skills=("PHP", "React"))
        self.repository.save(updated)
        self.assertEqual(self.repository.get("candidate-1"), updated)

        self.assertTrue(self.repository.delete("candidate-1"))
        self.assertIsNone(self.repository.get("candidate-1"))
        self.assertFalse(self.repository.delete("candidate-1"))


if __name__ == "__main__":
    unittest.main()
