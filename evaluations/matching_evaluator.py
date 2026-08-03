"""Simple offline metrics for labeled matching examples."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class MatchingEvaluation:
    count: int
    mean_absolute_error: float
    threshold_accuracy: float


class MatchingEvaluator:
    def evaluate(
        self,
        expected: Sequence[float],
        actual: Sequence[float],
        *,
        threshold: float = 0.7,
    ) -> MatchingEvaluation:
        if len(expected) != len(actual):
            raise ValueError("expected and actual scores must have equal lengths")
        if not expected:
            return MatchingEvaluation(0, 0.0, 0.0)
        error = sum(abs(left - right) for left, right in zip(expected, actual)) / len(expected)
        correct = sum(
            (left >= threshold) == (right >= threshold)
            for left, right in zip(expected, actual)
        )
        return MatchingEvaluation(len(expected), error, correct / len(expected))
