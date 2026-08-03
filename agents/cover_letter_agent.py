"""Create a conservative cover-letter draft for human review."""

from __future__ import annotations

from models import CandidateProfile, DocumentArtifact, JobPosting, MatchResult
from services import DocumentService


class CoverLetterAgent:
    def __init__(self, documents: DocumentService) -> None:
        self._documents = documents

    def draft(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        match: MatchResult,
    ) -> DocumentArtifact:
        strengths = ", ".join(match.matched_skills) or "the role's core requirements"
        content = (
            f"Dear {job.company} hiring team,\n\n"
            f"I am interested in the {job.title} position. My background includes {strengths}. "
            "I would welcome the opportunity to discuss how my experience could support your team.\n\n"
            f"Sincerely,\n{candidate.full_name}\n"
        )
        return self._documents.save_text(
            kind="cover-letter-draft",
            name=f"{candidate.candidate_id}-{job.job_id}",
            content=content,
        )
