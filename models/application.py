"""Application records, artifacts, and validation results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from utils.dates import from_iso, to_iso, utc_now


class ApplicationStatus(str, Enum):
    DRAFT = "draft"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    READY = "ready"
    SUBMITTED = "submitted"
    FAILED = "failed"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True, slots=True)
class DocumentArtifact:
    kind: str
    path: str
    content_hash: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class ApplicationValidation:
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Application:
    candidate_id: str
    job_id: str
    application_id: str = field(default_factory=lambda: uuid4().hex)
    status: ApplicationStatus = ApplicationStatus.DRAFT
    resume_path: str | None = None
    cover_letter_path: str | None = None
    notes: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    submitted_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "application_id": self.application_id,
            "candidate_id": self.candidate_id,
            "job_id": self.job_id,
            "status": self.status.value,
            "resume_path": self.resume_path,
            "cover_letter_path": self.cover_letter_path,
            "notes": self.notes,
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
            "submitted_at": to_iso(self.submitted_at),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Application":
        return cls(
            application_id=str(value["application_id"]),
            candidate_id=str(value["candidate_id"]),
            job_id=str(value["job_id"]),
            status=ApplicationStatus(value.get("status", ApplicationStatus.DRAFT.value)),
            resume_path=value.get("resume_path"),
            cover_letter_path=value.get("cover_letter_path"),
            notes=str(value.get("notes", "")),
            created_at=from_iso(value.get("created_at")) or utc_now(),
            updated_at=from_iso(value.get("updated_at")) or utc_now(),
            submitted_at=from_iso(value.get("submitted_at")),
        )
