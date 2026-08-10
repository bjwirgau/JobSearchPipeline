"""Evidence-grounded application form answer tests."""

from __future__ import annotations

import unittest
from typing import Any, Mapping

from agents import (
    ApplicationFormAgent,
    InvalidApplicationAnswerResponseError,
)
from models import (
    ApplicationFieldKind,
    ApplicationFormField,
    CandidateProfile,
    JobPosting,
    ResumeKnowledgeBase,
)


PROMPT = """\
CANDIDATE {candidate_profile}
KNOWLEDGE {resume_knowledge}
JOB {job_posting}
APPROVED {application_answers}
FIELDS {form_fields}
"""


class FakeLLM:
    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    async def generate_text(self, prompt: str) -> str:
        raise AssertionError("application answers must use structured output")

    async def generate_structured(
        self,
        prompt: str,
        *,
        schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.calls.append((prompt, schema))
        return self.response


class ApplicationFormAgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.candidate = CandidateProfile(
            candidate_id="candidate-1",
            full_name="Private Candidate",
            email="private@example.com",
            phone="555-123-4567",
            location="Denver, CO",
            summary="Builds reliable platforms.",
            skills=("Python",),
            application_answers={
                "Will you now or in the future require sponsorship?": "No",
            },
        )
        self.knowledge = ResumeKnowledgeBase(
            candidate_id="candidate-1",
            skills=("Python",),
        )
        self.job = JobPosting(
            source="greenhouse",
            external_id="job-1",
            title="Software Engineer",
            company="Example",
            url="https://example.com/jobs/1",
            description="Build software platforms.",
        )

    async def test_combines_local_contact_approved_and_llm_answers(self) -> None:
        llm = FakeLLM(
            {
                "answers": [
                    {
                        "field_id": "motivation",
                        "value": "My supported platform experience fits this role.",
                    }
                ],
                "unresolved": [],
            }
        )
        agent = ApplicationFormAgent(llm=llm, prompt_template=PROMPT)
        fields = (
            ApplicationFormField(
                "first-name",
                "First Name",
                ApplicationFieldKind.TEXT,
                required=True,
            ),
            ApplicationFormField(
                "email",
                "Email Address",
                ApplicationFieldKind.TEXT,
                required=True,
            ),
            ApplicationFormField(
                "sponsorship",
                "Will you now or in the future require sponsorship?",
                ApplicationFieldKind.RADIO,
                required=True,
                options=("Yes", "No"),
            ),
            ApplicationFormField(
                "motivation",
                "Why are you interested in this role?",
                ApplicationFieldKind.TEXTAREA,
                required=True,
            ),
            ApplicationFormField(
                "gender",
                "Gender identity *",
                ApplicationFieldKind.SELECT,
                options=("Woman", "Man", "Non-binary", "Decline to self-identify"),
            ),
            ApplicationFormField(
                "email-consent",
                "Email consent *",
                ApplicationFieldKind.TEXT,
                required=True,
            ),
        )

        result = await agent.answer(
            fields=fields,
            candidate=self.candidate,
            knowledge=self.knowledge,
            job=self.job,
        )

        self.assertEqual(result.answers["first-name"], "Private")
        self.assertEqual(result.answers["email"], "private@example.com")
        self.assertEqual(result.answers["sponsorship"], "No")
        self.assertIn("supported platform experience", result.answers["motivation"])
        self.assertEqual(
            [field.field_id for field in result.unresolved_fields],
            ["gender", "email-consent"],
        )
        self.assertEqual(len(llm.calls), 1)
        prompt, schema = llm.calls[0]
        self.assertNotIn(self.candidate.full_name, prompt)
        self.assertNotIn(self.candidate.email, prompt)
        field_enum = schema["properties"]["answers"]["items"]["properties"][
            "field_id"
        ]["enum"]
        self.assertEqual(field_enum, ["motivation"])

    async def test_rejects_an_answer_outside_select_options(self) -> None:
        llm = FakeLLM(
            {
                "answers": [{"field_id": "level", "value": "Expert"}],
                "unresolved": [],
            }
        )
        agent = ApplicationFormAgent(llm=llm, prompt_template=PROMPT)
        field = ApplicationFormField(
            "level",
            "Python proficiency",
            ApplicationFieldKind.SELECT,
            required=True,
            options=("Beginner", "Intermediate", "Advanced"),
        )

        with self.assertRaisesRegex(
            InvalidApplicationAnswerResponseError,
            "not a supported option",
        ):
            await agent.answer(
                fields=(field,),
                candidate=self.candidate,
                knowledge=self.knowledge,
                job=self.job,
            )


if __name__ == "__main__":
    unittest.main()
