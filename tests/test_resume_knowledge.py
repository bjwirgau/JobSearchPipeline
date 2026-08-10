"""Structured resume knowledge model and JSON service tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from models import CandidateProfile, ResumeKnowledgeBase
from services import ResumeKnowledgeError, ResumeKnowledgeService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ResumeKnowledgeTests(unittest.TestCase):
    def test_preserves_skill_years_not_repeated_in_skill_list(self) -> None:
        knowledge = ResumeKnowledgeBase.from_dict(
            {
                "candidate_id": "candidate-1",
                "skills": ["Magento", "PHP", "React"],
                "years": {"PHP": 10, "Magento": 10, "Java": 2},
                "industries": ["Ecommerce", "Retail"],
            }
        )

        self.assertEqual(knowledge.skills, ("Magento", "PHP", "React"))
        self.assertEqual(
            knowledge.all_skills,
            ("Magento", "PHP", "React", "Java"),
        )
        self.assertEqual(knowledge.years_for("php"), 10)
        self.assertEqual(knowledge.years_for("JAVA"), 2)

    def test_json_service_round_trips_validated_knowledge(self) -> None:
        knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("PHP", "React"),
            years={"PHP": 10, "React": 4},
            industries=("Ecommerce",),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume.json"
            service = ResumeKnowledgeService(path)

            self.assertEqual(service.save(knowledge), path)
            self.assertEqual(service.load(), knowledge)

    def test_saving_knowledge_preserves_profile_and_preferences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate_profile.json"
            path.write_text(
                json.dumps(
                    {
                        "candidate_id": "candidate-1",
                        "full_name": "Example Candidate",
                        "email": "candidate@example.com",
                        "phone": "(555) 123-4567",
                        "linkedin_url": "https://linkedin.com/in/example",
                        "github_url": "https://github.com/example",
                        "website_url": "https://example.dev",
                        "additional_keywords": ["Technical Leadership"],
                        "application_answers": {"Require sponsorship?": "No"},
                        "skills": ["PHP"],
                        "desired_titles": ["Backend Engineer"],
                    }
                ),
                encoding="utf-8",
            )
            service = ResumeKnowledgeService(path)
            service.save(
                ResumeKnowledgeBase(
                    candidate_id="candidate-1",
                    skills=("PHP", "React"),
                    years={"PHP": 10},
                    industries=("Ecommerce",),
                )
            )

            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(stored["full_name"], "Example Candidate")
            self.assertEqual(stored["phone"], "(555) 123-4567")
            self.assertEqual(
                stored["linkedin_url"], "https://linkedin.com/in/example"
            )
            self.assertEqual(stored["github_url"], "https://github.com/example")
            self.assertEqual(stored["website_url"], "https://example.dev")
            self.assertEqual(
                stored["additional_keywords"], ["Technical Leadership"]
            )
            self.assertEqual(stored["desired_titles"], ["Backend Engineer"])
            self.assertEqual(
                stored["application_answers"],
                {"Require sponsorship?": "No"},
            )
            self.assertEqual(stored["skills"], ["PHP", "React"])
            self.assertEqual(stored["years"], {"PHP": 10.0})

    def test_invalid_skill_years_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            ResumeKnowledgeBase(
                candidate_id="candidate-1",
                years={"PHP": -1},
            )

    def test_invalid_json_has_a_domain_specific_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "resume.json"
            path.write_text("{not-json}", encoding="utf-8")

            with self.assertRaisesRegex(ResumeKnowledgeError, "invalid resume knowledge JSON"):
                ResumeKnowledgeService(path).load()

    def test_unified_candidate_profile_loads_both_views(self) -> None:
        path = PROJECT_ROOT / "data" / "candidate_profile.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidate = CandidateProfile.from_dict(payload)
        knowledge = ResumeKnowledgeService(path).load()

        self.assertEqual(candidate.candidate_id, knowledge.candidate_id)
        self.assertEqual(candidate.phone, payload.get("phone", ""))
        self.assertEqual(candidate.linkedin_url, payload.get("linkedin_url", ""))
        self.assertEqual(candidate.github_url, payload.get("github_url", ""))
        self.assertEqual(candidate.website_url, payload.get("website_url", ""))
        self.assertEqual(
            candidate.additional_keywords,
            tuple(payload.get("additional_keywords", ())),
        )
        self.assertEqual(
            dict(candidate.application_answers),
            payload.get("application_answers", {}),
        )
        self.assertEqual(candidate.skills, knowledge.skills)
        self.assertIn("Magento", knowledge.all_skills)
        self.assertEqual(knowledge.years_for("Magento"), 10)
        self.assertIn("Ecommerce", knowledge.industries)
        self.assertEqual(knowledge.roles[0].location, "El Paso, TX")
        self.assertIn(
            "Developed a full-stack e-commerce platform",
            knowledge.roles[0].responsibilities[0],
        )
        self.assertEqual(knowledge.achievements[0].category, "Performance")
        self.assertIn("Lighthouse", knowledge.achievements[0].description)
        self.assertEqual(
            knowledge.certifications[0].name,
            "Adobe Certified Expert - Adobe Commerce Developer",
        )
        self.assertEqual(
            knowledge.education[0].institution,
            "University of San Diego",
        )
        self.assertEqual(knowledge.education[0].field, "Applied Artificial Intelligence")


if __name__ == "__main__":
    unittest.main()
