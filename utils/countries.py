"""Country-code normalization and remote-work eligibility matching."""

from __future__ import annotations

import re
from collections.abc import Iterable


COUNTRY_NAMES: dict[str, tuple[str, ...]] = {
    "at": ("austria",),
    "au": ("australia",),
    "be": ("belgium",),
    "br": ("brazil",),
    "ca": ("canada",),
    "ch": ("switzerland",),
    "de": ("germany",),
    "dk": ("denmark",),
    "es": ("spain",),
    "fi": ("finland",),
    "fr": ("france",),
    "gb": ("united kingdom", "great britain", "britain", "uk"),
    "ie": ("ireland",),
    "in": ("india",),
    "it": ("italy",),
    "jp": ("japan",),
    "kr": ("south korea", "korea"),
    "mx": ("mexico",),
    "nl": ("netherlands",),
    "no": ("norway",),
    "nz": ("new zealand",),
    "pl": ("poland",),
    "pt": ("portugal",),
    "se": ("sweden",),
    "sg": ("singapore",),
    "us": ("united states of america", "united states", "usa", "u s a", "u s"),
    "za": ("south africa",),
}

REGION_COUNTRIES: dict[str, frozenset[str]] = {
    "north america": frozenset({"ca", "mx", "us"}),
    "americas": frozenset({"br", "ca", "mx", "us"}),
    "latin america": frozenset({"br", "mx"}),
    "latam": frozenset({"br", "mx"}),
    "europe": frozenset(
        {
            "at",
            "be",
            "ch",
            "de",
            "dk",
            "es",
            "fi",
            "fr",
            "gb",
            "ie",
            "it",
            "nl",
            "no",
            "pl",
            "pt",
            "se",
        }
    ),
    "european union": frozenset(
        {
            "at",
            "be",
            "de",
            "dk",
            "es",
            "fi",
            "fr",
            "ie",
            "it",
            "nl",
            "pl",
            "pt",
            "se",
        }
    ),
    "apac": frozenset({"au", "in", "jp", "kr", "nz", "sg"}),
    "asia pacific": frozenset({"au", "in", "jp", "kr", "nz", "sg"}),
}

WORLDWIDE_MARKERS = (
    "any location",
    "anywhere",
    "global",
    "worldwide",
    "world wide",
)


def normalize_country_code(value: str) -> str:
    code = value.strip().casefold()
    if len(code) != 2 or not code.isalpha():
        raise ValueError("country must be a two-letter country code")
    return code


def country_codes_from_text(value: str) -> tuple[str, ...]:
    """Extract explicit countries or broad eligibility regions from location text."""

    normalized = _words(value)
    found: set[str] = set()
    for code, aliases in COUNTRY_NAMES.items():
        if any(_contains(normalized, alias) for alias in aliases):
            found.add(code)
    for region, countries in REGION_COUNTRIES.items():
        if _contains(normalized, region):
            found.update(countries)

    # Two-letter location codes are accepted only when uppercase in the source,
    # avoiding false matches for ordinary words such as "in" and "us".
    found.update(
        token.casefold()
        for token in re.findall(r"(?<![A-Za-z])[A-Z]{2}(?![A-Za-z])", value)
        if token.casefold() in COUNTRY_NAMES
    )
    stripped = value.strip().casefold()
    if stripped in COUNTRY_NAMES:
        found.add(stripped)
    if not found and any(
        _contains(normalized, marker) for marker in WORLDWIDE_MARKERS
    ):
        return ("*",)
    return tuple(sorted(found))


def remote_country_is_eligible(
    requested_country: str,
    eligible_country_codes: Iterable[str],
    location: str,
) -> bool:
    requested = normalize_country_code(requested_country)
    eligible = {
        value.strip().casefold()
        for value in eligible_country_codes
        if value.strip()
    }
    if "*" in eligible or requested in eligible:
        return True
    if eligible:
        return False
    inferred = set(country_codes_from_text(location))
    return "*" in inferred or requested in inferred


def _words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _contains(normalized: str, term: str) -> bool:
    return f" {term} " in f" {normalized} "
