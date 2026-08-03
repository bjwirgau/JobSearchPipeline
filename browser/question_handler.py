"""Identify application questions that require human answers."""

from __future__ import annotations

from typing import Mapping


class QuestionHandler:
    def unresolved(
        self,
        questions: tuple[str, ...],
        known_answers: Mapping[str, str],
    ) -> tuple[str, ...]:
        return tuple(question for question in questions if not known_answers.get(question, "").strip())
