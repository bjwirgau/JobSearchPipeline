"""Normalize heterogeneous source records into shared JobPosting models."""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Mapping, Sequence

from models import JobPosting
from utils.hashing import stable_hash
from utils.countries import country_codes_from_text
from utils.text import normalize_text


DEFAULT_SKILLS = (
    "Adobe Commerce",
    "Magento",
    "PHP",
    "Laravel",
    "React",
    "JavaScript",
    "TypeScript",
    "Python",
    "Java",
    "MySQL",
    "PostgreSQL",
    "SQL",
    "REST APIs",
    "GraphQL",
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Git",
    "CI/CD",
    "Linux",
    "LangGraph",
    "MLflow",
)

SALARY_PATTERN = re.compile(
    r"\$\s*(?P<minimum>\d[\d,]*(?:\.\d{2})?)"
    r"(?:\s*(?:/[a-z]+|per\s+[a-z]+)?\s*(?:-|–|—|to)\s*\$?\s*"
    r"(?P<maximum>\d[\d,]*(?:\.\d{2})?))?",
    re.IGNORECASE,
)


def _contains_skill(text: str, skill: str) -> bool:
    term = re.escape(normalize_text(skill)).replace(r"\ ", r"\s+")
    pattern = rf"(?<![a-z0-9+#]){term}(?![a-z0-9+#])"
    return re.search(pattern, text) is not None


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def html_to_text(value: str) -> str:
    if "<" not in value:
        return " ".join(html.unescape(value).split())
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        parser = _TextExtractor()
        parser.feed(html.unescape(value))
        return " ".join(parser.parts)
    return " ".join(BeautifulSoup(html.unescape(value), "html.parser").get_text(" ").split())


def parse_datetime(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    text = str(value).strip()
    relative = re.fullmatch(
        r"(?:about\s+)?(?P<count>\d+|a|an|one)\s+"
        r"(?P<unit>minute|hour|day|week|month)s?\s+ago",
        text.casefold(),
    )
    if relative:
        raw_count = relative.group("count")
        count = 1 if raw_count in {"a", "an", "one"} else int(raw_count)
        unit_days = {"day": 1, "week": 7, "month": 30}
        unit = relative.group("unit")
        if unit == "minute":
            delta = timedelta(minutes=count)
        elif unit == "hour":
            delta = timedelta(hours=count)
        else:
            delta = timedelta(days=count * unit_days[unit])
        return datetime.now(timezone.utc) - delta
    if text.casefold() in {"just now", "today"}:
        return datetime.now(timezone.utc)
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def parse_salary(value: str) -> tuple[int | None, int | None, str | None]:
    match = SALARY_PATTERN.search(value)
    if not match:
        return None, None, None
    minimum = int(float(match.group("minimum").replace(",", "")))
    maximum_value = match.group("maximum")
    maximum = (
        int(float(maximum_value.replace(",", "")))
        if maximum_value
        else None
    )
    return minimum, maximum, "USD"


class JobNormalizer:
    def __init__(self, skill_vocabulary: Sequence[str] = DEFAULT_SKILLS) -> None:
        unique = {
            normalize_text(skill): skill.strip()
            for skill in skill_vocabulary
            if skill.strip()
        }
        self._skill_vocabulary = tuple(unique.values())

    def normalize(
        self,
        *,
        source: str,
        external_id: object,
        title: object,
        company: object,
        url: object,
        location: object = "",
        description: object = "",
        skills: Sequence[str] = (),
        industries: Sequence[str] = (),
        responsibilities: Sequence[str] = (),
        requirements: Sequence[str] = (),
        employment_type: object = None,
        salary_min: object = None,
        salary_max: object = None,
        salary_currency: object = None,
        is_remote: bool | None = None,
        remote_country_codes: Sequence[str] = (),
        posted_at: object = None,
        raw: Mapping[str, Any] | None = None,
    ) -> JobPosting:
        clean_description = html_to_text(str(description or ""))
        clean_title = str(title or "").strip()
        clean_location = str(location or "").strip()
        searchable = normalize_text(f"{clean_title} {clean_description}")
        inferred_skills = tuple(
            skill
            for skill in self._skill_vocabulary
            if _contains_skill(searchable, skill)
        )
        normalized_skills = tuple(
            dict.fromkeys(
                str(skill).strip()
                for skill in (*skills, *inferred_skills)
                if str(skill).strip()
            )
        )
        normalized_industries = tuple(
            dict.fromkeys(str(value).strip() for value in industries if str(value).strip())
        )
        normalized_responsibilities = tuple(
            dict.fromkeys(
                html_to_text(str(value)) for value in responsibilities if str(value).strip()
            )
        )
        normalized_requirements = tuple(
            dict.fromkeys(
                html_to_text(str(value)) for value in requirements if str(value).strip()
            )
        )
        inferred_salary = parse_salary(clean_description)
        minimum = self._integer(salary_min)
        maximum = self._integer(salary_max)
        currency = str(salary_currency).strip() if salary_currency else None
        if minimum is None and maximum is None:
            minimum, maximum, inferred_currency = inferred_salary
            currency = currency or inferred_currency
        remote = is_remote
        if remote is None:
            remote = "remote" in normalize_text(
                f"{clean_title} {clean_location} {clean_description}"
            )
        normalized_remote_countries = tuple(
            dict.fromkeys(
                str(value).strip().casefold()
                for value in remote_country_codes
                if str(value).strip()
            )
        )
        if remote and not normalized_remote_countries:
            normalized_remote_countries = country_codes_from_text(clean_location)
        clean_url = str(url or "").strip()
        identifier = str(external_id or "").strip() or stable_hash(clean_url)
        return JobPosting(
            source=source,
            external_id=identifier,
            title=clean_title,
            company=str(company or "").strip(),
            url=clean_url,
            location=clean_location,
            description=clean_description,
            skills=normalized_skills,
            industries=normalized_industries,
            responsibilities=normalized_responsibilities,
            requirements=normalized_requirements,
            employment_type=(
                str(employment_type).strip() if employment_type else None
            ),
            salary_min=minimum,
            salary_max=maximum,
            salary_currency=currency,
            is_remote=remote,
            remote_country_codes=normalized_remote_countries,
            posted_at=parse_datetime(posted_at),
            raw=raw or {},
        )

    @staticmethod
    def _integer(value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            return None
