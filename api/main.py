"""Optional FastAPI composition kept behind a lazy dependency import."""

from __future__ import annotations

from .dependencies import ApiDependencies
from .routes import list_job_prospects, list_matches


def create_app(dependencies: ApiDependencies):
    try:
        from fastapi import FastAPI
    except ImportError as error:
        raise RuntimeError("install the API dependencies with: pip install -e '.[api]'") from error

    app = FastAPI(title="Job Agent API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": "1"}

    @app.get("/job-prospects")
    def job_prospects(limit: int = 100):
        return list_job_prospects(dependencies.job_prospects, limit=limit)

    @app.get("/matches")
    def matches():
        return list_matches()

    return app
