"""Local generated-document persistence."""

from __future__ import annotations

from pathlib import Path

from models import DocumentArtifact
from utils.hashing import stable_hash


class DocumentService:
    def __init__(self, output_directory: str | Path) -> None:
        self._output_directory = Path(output_directory)

    def save_text(self, *, kind: str, name: str, content: str) -> DocumentArtifact:
        safe_kind = self._safe_component(kind)
        safe_name = self._safe_component(name)
        self._output_directory.mkdir(parents=True, exist_ok=True)
        path = self._output_directory / f"{safe_name}-{safe_kind}.md"
        path.write_text(content, encoding="utf-8")
        return DocumentArtifact(
            kind=safe_kind,
            path=str(path),
            content_hash=stable_hash(content),
        )

    @staticmethod
    def _safe_component(value: str) -> str:
        normalized = "-".join(value.casefold().split())
        safe = "".join(character for character in normalized if character.isalnum() or character == "-")
        if not safe:
            raise ValueError("document names must contain letters or numbers")
        return safe
