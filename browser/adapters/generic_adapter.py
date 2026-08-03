"""Generic application-page identification and field mapping."""

from __future__ import annotations

from models import Application, CandidateProfile


class GenericAdapter:
    platform = "generic"

    def supports(self, url: str) -> bool:
        return url.startswith(("https://", "http://"))

    def field_values(
        self,
        candidate: CandidateProfile,
        application: Application,
    ) -> dict[str, str]:
        return {
            "name": candidate.full_name,
            "email": candidate.email,
            "location": candidate.location,
            "resume": application.resume_path or "",
            "cover_letter": application.cover_letter_path or "",
        }
