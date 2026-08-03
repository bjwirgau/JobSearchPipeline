"""Text normalization used by parsing and matching."""

from __future__ import annotations

import re


TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9+#.\-]*")


def normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def tokenize(value: str) -> tuple[str, ...]:
    return tuple(match.group(0).casefold() for match in TOKEN_PATTERN.finditer(value))
