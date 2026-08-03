"""Load, validate, and write structured resume knowledge JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from models import CandidateProfile, ResumeKnowledgeBase


class ResumeKnowledgeError(ValueError):
    pass


class ResumeKnowledgeService:
    def __init__(self, default_path: str | Path) -> None:
        self.default_path = Path(default_path)

    def load(
        self,
        path: str | Path | None = None,
        *,
        candidate_id: str | None = None,
    ) -> ResumeKnowledgeBase:
        source = Path(path) if path is not None else self.default_path
        try:
            value = json.loads(source.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ResumeKnowledgeError(f"resume knowledge file not found: {source}") from error
        except json.JSONDecodeError as error:
            raise ResumeKnowledgeError(
                f"invalid resume knowledge JSON at line {error.lineno}, column {error.colno}"
            ) from error
        if not isinstance(value, Mapping):
            raise ResumeKnowledgeError("resume knowledge JSON must contain an object")
        try:
            return ResumeKnowledgeBase.from_dict(value, candidate_id=candidate_id)
        except (KeyError, TypeError, ValueError) as error:
            raise ResumeKnowledgeError(f"invalid resume knowledge: {error}") from error

    def save(
        self,
        knowledge: ResumeKnowledgeBase,
        path: str | Path | None = None,
    ) -> Path:
        destination = Path(path) if path is not None else self.default_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing: dict[str, Any] = {}
        if destination.exists():
            try:
                stored_value = json.loads(destination.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ResumeKnowledgeError(
                    f"cannot update invalid profile JSON at line {error.lineno}, "
                    f"column {error.colno}"
                ) from error
            if not isinstance(stored_value, Mapping):
                raise ResumeKnowledgeError("candidate profile JSON must contain an object")
            existing.update(stored_value)
        existing.update(knowledge.to_dict())
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(existing, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    @staticmethod
    def from_candidate(candidate: CandidateProfile) -> ResumeKnowledgeBase:
        return ResumeKnowledgeBase(
            candidate_id=candidate.candidate_id,
            skills=candidate.skills,
        )
