"""Validated, evidence-linked content for a tailored cover letter."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable
from typing import Any, Mapping


COVER_LETTER_MAX_WORDS = 350


class InvalidGeneratedCoverLetterError(ValueError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidGeneratedCoverLetterError(f"{field} must be a string")
    cleaned = " ".join(value.split())
    if not cleaned:
        raise InvalidGeneratedCoverLetterError(f"{field} must not be empty")
    return cleaned


@dataclass(frozen=True, slots=True)
class GeneratedCoverLetterParagraph:
    text: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "text",
            _text(self.text, "cover-letter paragraph text"),
        )
        cleaned_ids = tuple(
            dict.fromkeys(
                _text(evidence_id, "cover-letter evidence ID")
                for evidence_id in self.evidence_ids
            )
        )
        if not cleaned_ids:
            raise InvalidGeneratedCoverLetterError(
                "cover-letter paragraph evidence_ids must not be empty"
            )
        object.__setattr__(self, "evidence_ids", cleaned_ids)

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "GeneratedCoverLetterParagraph":
        raw_ids = value.get("evidence_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            raise InvalidGeneratedCoverLetterError(
                "cover-letter paragraph evidence_ids must be a non-empty array"
            )
        evidence_ids: list[str] = []
        for raw_id in raw_ids:
            evidence_id = _text(raw_id, "cover-letter evidence ID")
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        return cls(
            text=_text(value.get("text"), "cover-letter paragraph text"),
            evidence_ids=tuple(evidence_ids),
        )


@dataclass(frozen=True, slots=True)
class GeneratedCoverLetterContent:
    paragraphs: tuple[GeneratedCoverLetterParagraph, ...]

    def __post_init__(self) -> None:
        if not 3 <= len(self.paragraphs) <= 4:
            raise InvalidGeneratedCoverLetterError(
                "cover letter must contain between 3 and 4 paragraphs"
            )
        if self.word_count > COVER_LETTER_MAX_WORDS:
            raise InvalidGeneratedCoverLetterError(
                "cover letter exceeds the 350-word one-page limit"
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GeneratedCoverLetterContent":
        raw_paragraphs = value.get("paragraphs")
        if not isinstance(raw_paragraphs, list):
            raise InvalidGeneratedCoverLetterError(
                "cover-letter paragraphs must be an array"
            )
        paragraphs: list[GeneratedCoverLetterParagraph] = []
        for value in raw_paragraphs:
            if not isinstance(value, Mapping):
                raise InvalidGeneratedCoverLetterError(
                    "each cover-letter paragraph must be an object"
                )
            paragraphs.append(GeneratedCoverLetterParagraph.from_dict(value))
        return cls(tuple(paragraphs))

    @property
    def word_count(self) -> int:
        return sum(len(paragraph.text.split()) for paragraph in self.paragraphs)

    def validate_evidence(self, allowed_evidence_ids: Iterable[str]) -> None:
        allowed = set(allowed_evidence_ids)
        unknown = sorted(
            {
                evidence_id
                for paragraph in self.paragraphs
                for evidence_id in paragraph.evidence_ids
                if evidence_id not in allowed
            }
        )
        if unknown:
            raise InvalidGeneratedCoverLetterError(
                "cover letter cites unknown evidence IDs: " + ", ".join(unknown)
            )
