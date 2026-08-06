"""MySQL resume-knowledge repository tests."""

from __future__ import annotations

import unittest
from dataclasses import replace

from database import Database, MySQLConfig, initialize_schema
from models import ResumeKnowledgeBase
from repositories import ResumeKnowledgeRepository
from tests.mysql_fakes import FakeMySQLServer


class ResumeKnowledgeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = ResumeKnowledgeRepository(database)

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
