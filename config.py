"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class SourceTarget:
    company: str
    value: str


def _source_targets(value: str | None) -> tuple[SourceTarget, ...]:
    if not value:
        return ()
    targets: list[SourceTarget] = []
    for item in value.split(";"):
        company, separator, target = item.partition("=")
        company = company.strip()
        target = target.strip()
        if not separator or not company or not target:
            raise ValueError(
                "job source targets must use Company=token-or-url entries separated by semicolons"
            )
        targets.append(SourceTarget(company, target))
    return tuple(targets)


def _as_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"invalid environment entry at {path}:{line_number}")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with automation disabled unless explicitly enabled."""

    environment: str = "development"
    log_level: str = "INFO"
    database_path: Path = PROJECT_ROOT / "data" / "job_agent.sqlite3"
    candidate_profile_path: Path = PROJECT_ROOT / "data" / "candidate_profile.json"
    generated_documents_dir: Path = PROJECT_ROOT / "data" / "generated_documents"
    search_enabled: bool = False
    remote_country: str | None = None
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_country: str = "us"
    remotive_enabled: bool = False
    usajobs_email: str | None = None
    usajobs_api_key: str | None = None
    linkedin_enabled: bool = False
    apify_api_token: str | None = None
    apify_linkedin_actor_id: str = "automation-lab/linkedin-jobs-scraper"
    apify_timeout_seconds: float = 120.0
    greenhouse_boards: tuple[SourceTarget, ...] = ()
    lever_sites: tuple[SourceTarget, ...] = ()
    workday_tenants: tuple[SourceTarget, ...] = ()
    career_pages: tuple[SourceTarget, ...] = ()
    browser_fallback: str = "none"
    http_timeout_seconds: float = 20.0
    http_user_agent: str = "JobAgent/0.3 (+local-job-search)"
    application_submission_enabled: bool = False
    openai_api_key: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        if env is None:
            values = {**_read_env_file(PROJECT_ROOT / ".env"), **os.environ}
        else:
            values = env
        return cls(
            environment=values.get("JOB_AGENT_ENVIRONMENT", "development"),
            log_level=values.get("JOB_AGENT_LOG_LEVEL", "INFO").upper(),
            database_path=_resolve_path(
                values.get("JOB_AGENT_DATABASE_PATH", "data/job_agent.sqlite3"),
                PROJECT_ROOT,
            ),
            candidate_profile_path=_resolve_path(
                values.get("JOB_AGENT_CANDIDATE_PROFILE", "data/candidate_profile.json"),
                PROJECT_ROOT,
            ),
            generated_documents_dir=_resolve_path(
                values.get(
                    "JOB_AGENT_GENERATED_DOCUMENTS",
                    "data/generated_documents",
                ),
                PROJECT_ROOT,
            ),
            search_enabled=_as_bool(values.get("JOB_AGENT_SEARCH_ENABLED")),
            remote_country=(
                values.get("JOB_AGENT_REMOTE_COUNTRY", "").strip().casefold() or None
            ),
            adzuna_app_id=values.get("JOB_AGENT_ADZUNA_APP_ID") or None,
            adzuna_app_key=values.get("JOB_AGENT_ADZUNA_APP_KEY") or None,
            adzuna_country=values.get("JOB_AGENT_ADZUNA_COUNTRY", "us").casefold(),
            remotive_enabled=_as_bool(values.get("JOB_AGENT_REMOTIVE_ENABLED")),
            usajobs_email=values.get("JOB_AGENT_USAJOBS_EMAIL") or None,
            usajobs_api_key=values.get("JOB_AGENT_USAJOBS_API_KEY") or None,
            linkedin_enabled=_as_bool(
                values.get("JOB_AGENT_LINKEDIN_ENABLED")
            ),
            apify_api_token=values.get("JOB_AGENT_APIFY_API_TOKEN") or None,
            apify_linkedin_actor_id=values.get(
                "JOB_AGENT_APIFY_LINKEDIN_ACTOR_ID",
                "automation-lab/linkedin-jobs-scraper",
            ),
            apify_timeout_seconds=float(
                values.get("JOB_AGENT_APIFY_TIMEOUT_SECONDS", "120")
            ),
            greenhouse_boards=_source_targets(
                values.get("JOB_AGENT_GREENHOUSE_BOARDS")
            ),
            lever_sites=_source_targets(values.get("JOB_AGENT_LEVER_SITES")),
            workday_tenants=_source_targets(values.get("JOB_AGENT_WORKDAY_TENANTS")),
            career_pages=_source_targets(values.get("JOB_AGENT_CAREER_PAGES")),
            browser_fallback=values.get("JOB_AGENT_BROWSER_FALLBACK", "none").casefold(),
            http_timeout_seconds=float(
                values.get("JOB_AGENT_HTTP_TIMEOUT_SECONDS", "20")
            ),
            http_user_agent=values.get(
                "JOB_AGENT_HTTP_USER_AGENT",
                "JobAgent/0.3 (+local-job-search)",
            ),
            application_submission_enabled=_as_bool(
                values.get("JOB_AGENT_APPLICATION_SUBMISSION_ENABLED")
            ),
            openai_api_key=values.get("OPENAI_API_KEY") or None,
        )

    def __post_init__(self) -> None:
        if self.remote_country is not None and (
            len(self.remote_country) != 2 or not self.remote_country.isalpha()
        ):
            raise ValueError(
                "JOB_AGENT_REMOTE_COUNTRY must be a two-letter country code"
            )
        if bool(self.adzuna_app_id) != bool(self.adzuna_app_key):
            raise ValueError(
                "JOB_AGENT_ADZUNA_APP_ID and JOB_AGENT_ADZUNA_APP_KEY must be set together"
            )
        if len(self.adzuna_country) != 2 or not self.adzuna_country.isalpha():
            raise ValueError("JOB_AGENT_ADZUNA_COUNTRY must be a two-letter country code")
        if bool(self.usajobs_email) != bool(self.usajobs_api_key):
            raise ValueError(
                "JOB_AGENT_USAJOBS_EMAIL and JOB_AGENT_USAJOBS_API_KEY must be set together"
            )
        if not self.apify_linkedin_actor_id.strip() or any(
            character.isspace() for character in self.apify_linkedin_actor_id
        ):
            raise ValueError(
                "JOB_AGENT_APIFY_LINKEDIN_ACTOR_ID must be a non-empty Actor ID"
            )
        if self.apify_timeout_seconds <= 0 or self.apify_timeout_seconds > 300:
            raise ValueError(
                "JOB_AGENT_APIFY_TIMEOUT_SECONDS must be between 1 and 300"
            )
        if self.browser_fallback not in {"none", "playwright", "selenium"}:
            raise ValueError("JOB_AGENT_BROWSER_FALLBACK must be none, playwright, or selenium")
        if self.http_timeout_seconds <= 0:
            raise ValueError("JOB_AGENT_HTTP_TIMEOUT_SECONDS must be greater than zero")

    def prepare_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.candidate_profile_path.parent.mkdir(parents=True, exist_ok=True)
        self.generated_documents_dir.mkdir(parents=True, exist_ok=True)
