"""Application safety and completeness validation."""

from __future__ import annotations

from models import Application, ApplicationStatus, ApplicationValidation, CandidateProfile, JobPosting, MatchResult


class ValidationAgent:
    def validate(
        self,
        *,
        candidate: CandidateProfile,
        job: JobPosting,
        application: Application,
        match: MatchResult | None = None,
        user_approved: bool = False,
    ) -> ApplicationValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if "@" not in candidate.email:
            errors.append("candidate email is invalid")
        if not job.url.startswith(("https://", "http://")):
            errors.append("job URL must use HTTP or HTTPS")
        if not application.resume_path:
            errors.append("a resume document is required")
        if application.status not in {ApplicationStatus.APPROVED, ApplicationStatus.READY}:
            errors.append("application must be approved before submission")
        if not user_approved:
            errors.append("explicit user approval is required")
        if match and match.score < 0.6:
            warnings.append("match score is below the default review threshold")
        return ApplicationValidation(not errors, tuple(errors), tuple(warnings))
