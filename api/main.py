"""Optional FastAPI composition kept behind a lazy dependency import."""

from __future__ import annotations

from .dependencies import ApiDependencies
from .routes import list_applications, list_jobs, list_matches


def create_app(dependencies: ApiDependencies):
    try:
        from fastapi import FastAPI
    except ImportError as error:
        raise RuntimeError("install the API dependencies with: pip install -e '.[api]'") from error

    app = FastAPI(title="Job Agent API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "phase": "1"}

    @app.get("/jobs")
    def jobs(limit: int = 100):
        return list_jobs(dependencies.jobs, limit=limit)

    @app.get("/matches")
    def matches():
        return list_matches()

    @app.get("/applications")
    def applications():
        return list_applications(dependencies.applications)

    return app
