"""Environment-based application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parent


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
            application_submission_enabled=_as_bool(
                values.get("JOB_AGENT_APPLICATION_SUBMISSION_ENABLED")
            ),
            openai_api_key=values.get("OPENAI_API_KEY") or None,
        )

    def prepare_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.generated_documents_dir.mkdir(parents=True, exist_ok=True)
