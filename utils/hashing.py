"""Stable identities for deduplication and storage."""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_KEYS = {"ref", "source", "trackingid", "trk"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_QUERY_KEYS
            and not key.casefold().startswith(TRACKING_QUERY_PREFIXES)
        )
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.casefold(), parts.netloc.casefold(), path, query, "")
    )


def stable_hash(*values: str, length: int = 24) -> str:
    payload = "\x1f".join(value.strip().casefold() for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def stable_bytes_hash(value: bytes, *, length: int = 24) -> str:
    return hashlib.sha256(value).hexdigest()[:length]
