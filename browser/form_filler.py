"""Build form-fill plans without interacting with a live page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class FormFillPlan:
    values: Mapping[str, str]
    missing_required_fields: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return not self.missing_required_fields


class FormFiller:
    def plan(
        self,
        values: Mapping[str, str],
        *,
        required_fields: tuple[str, ...],
    ) -> FormFillPlan:
        missing = tuple(field for field in required_fields if not values.get(field, "").strip())
        return FormFillPlan(dict(values), missing)
