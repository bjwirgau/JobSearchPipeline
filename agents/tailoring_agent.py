"""Create a reviewable local resume-tailoring brief."""

from __future__ import annotations

from models import CandidateProfile, DocumentArtifact, JobPosting, MatchResult
from services import DocumentService


class TailoringAgent:
    def __init__(self, documents: DocumentService) -> None:
        self._documents = documents

    def create_brief(
        self,
        candidate: CandidateProfile,
        job: JobPosting,
        match: MatchResult,
    ) -> DocumentArtifact:
        content = "\n".join(
            (
                f"# Resume tailoring brief: {job.title} at {job.company}",
                "",
                f"Candidate: {candidate.full_name}",
                f"Match score: {match.score:.0%}",
                f"Skills to emphasize: {', '.join(match.matched_skills) or 'None identified'}",
                f"Gaps to review honestly: {', '.join(match.missing_skills) or 'None identified'}",
                "",
                "Review this brief before changing the source resume.",
            )
        )
        return self._documents.save_text(
            kind="resume-brief",
            name=f"{candidate.candidate_id}-{job.job_id}",
            content=content,
        )
