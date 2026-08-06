"""Framework-independent route handler functions."""

from .jobs import list_job_prospects
from .matches import list_matches

__all__ = ["list_job_prospects", "list_matches"]
