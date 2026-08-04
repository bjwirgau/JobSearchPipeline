"""Normalized adapters for supported job-posting sources."""

from .adzuna import AdzunaCredentials, AdzunaJobSource
from .career_page import CareerPage, CareerPageJobSource
from .greenhouse import GreenhouseBoard, GreenhouseJobSource
from .lever import LeverJobSource, LeverSite
from .linkedin import AuthorizedLinkedInClient, LinkedInJobSource
from .remotive import RemotiveJobSource
from .usajobs import USAJobsCredentials, USAJobsJobSource
from .workday import WorkdayJobSource, WorkdayTenant

__all__ = [
    "AdzunaCredentials",
    "AdzunaJobSource",
    "AuthorizedLinkedInClient",
    "CareerPage",
    "CareerPageJobSource",
    "GreenhouseBoard",
    "GreenhouseJobSource",
    "LeverJobSource",
    "LeverSite",
    "LinkedInJobSource",
    "RemotiveJobSource",
    "USAJobsCredentials",
    "USAJobsJobSource",
    "WorkdayJobSource",
    "WorkdayTenant",
]
