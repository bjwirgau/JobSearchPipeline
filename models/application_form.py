"""Browser-neutral application form fields and fill outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ApplicationFieldKind(str, Enum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SELECT = "select"
    COMBOBOX = "combobox"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    FILE = "file"


@dataclass(frozen=True, slots=True)
class ApplicationFormField:
    field_id: str
    label: str
    kind: ApplicationFieldKind
    required: bool = False
    options: tuple[str, ...] = ()
    current_value: str = ""

    def __post_init__(self) -> None:
        field_id = self.field_id.strip()
        label = self.label.strip()
        if not field_id:
            raise ValueError("application field_id must not be empty")
        if not label:
            raise ValueError("application field label must not be empty")
        object.__setattr__(self, "field_id", field_id)
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "current_value", self.current_value.strip())
        options = tuple(
            dict.fromkeys(option.strip() for option in self.options if option.strip())
        )
        object.__setattr__(self, "options", options)
        if self.kind in {ApplicationFieldKind.SELECT, ApplicationFieldKind.RADIO}:
            if not options:
                raise ValueError(f"{self.kind.value} fields must define options")
        elif options:
            raise ValueError(
                f"{self.kind.value} fields must not define selectable options"
            )


@dataclass(frozen=True, slots=True)
class ApplicationFillResult:
    filled_field_ids: tuple[str, ...] = ()
    unresolved_required_fields: tuple[ApplicationFormField, ...] = ()
    failures: tuple[str, ...] = ()
    resume_uploaded: bool = False

    @property
    def complete(self) -> bool:
        return not self.unresolved_required_fields and not self.failures
