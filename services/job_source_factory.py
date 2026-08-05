"""Build configured job sources without importing optional clients at startup."""

from __future__ import annotations

from collections.abc import Sequence

from browser import PlaywrightPageLoader, SeleniumPageLoader
from config import Settings

from .http_service import RequestsHttpClient
from .job_normalization_service import DEFAULT_SKILLS, JobNormalizer
from .job_source_service import JobSourceService
from .job_sources import (
    AdzunaCredentials,
    AdzunaJobSource,
    ApifyLinkedInConfig,
    CareerPage,
    CareerPageJobSource,
    GreenhouseBoard,
    GreenhouseJobSource,
    LeverJobSource,
    LeverSite,
    LinkedInJobSource,
    RemotiveJobSource,
    USAJobsCredentials,
    USAJobsJobSource,
    WorkdayJobSource,
    WorkdayTenant,
)


def build_job_sources(
    settings: Settings,
    *,
    skill_vocabulary: Sequence[str] = (),
) -> tuple[JobSourceService, ...]:
    http = RequestsHttpClient(
        timeout_seconds=settings.http_timeout_seconds,
        user_agent=settings.http_user_agent,
    )
    normalizer = JobNormalizer((*DEFAULT_SKILLS, *skill_vocabulary))
    browser_loader = None
    if settings.browser_fallback == "playwright":
        browser_loader = PlaywrightPageLoader(
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.http_user_agent,
        )
    elif settings.browser_fallback == "selenium":
        browser_loader = SeleniumPageLoader(
            timeout_seconds=settings.http_timeout_seconds,
            user_agent=settings.http_user_agent,
        )

    sources: list[JobSourceService] = []
    if settings.adzuna_app_id and settings.adzuna_app_key:
        sources.append(
            AdzunaJobSource(
                AdzunaCredentials(
                    settings.adzuna_app_id,
                    settings.adzuna_app_key,
                    settings.adzuna_country,
                ),
                http=http,
                normalizer=normalizer,
            )
        )
    if settings.remotive_enabled:
        sources.append(RemotiveJobSource(http=http, normalizer=normalizer))
    if settings.usajobs_email and settings.usajobs_api_key:
        sources.append(
            USAJobsJobSource(
                USAJobsCredentials(settings.usajobs_email, settings.usajobs_api_key),
                http=http,
                normalizer=normalizer,
            )
        )
    if settings.apify_api_token:
        apify_http = RequestsHttpClient(
            timeout_seconds=settings.apify_timeout_seconds + 10,
            user_agent=settings.http_user_agent,
        )
        sources.append(
            LinkedInJobSource(
                ApifyLinkedInConfig(
                    api_token=settings.apify_api_token,
                    actor_id=settings.apify_linkedin_actor_id,
                    timeout_seconds=settings.apify_timeout_seconds,
                ),
                http=apify_http,
                normalizer=normalizer,
            )
        )

    # Direct ATS and career-page adapters are optional supplemental sources.
    if settings.greenhouse_boards:
        sources.append(
            GreenhouseJobSource(
                tuple(
                    GreenhouseBoard(target.company, target.value)
                    for target in settings.greenhouse_boards
                ),
                http=http,
                normalizer=normalizer,
            )
        )
    if settings.lever_sites:
        sources.append(
            LeverJobSource(
                tuple(
                    LeverSite(target.company, target.value)
                    for target in settings.lever_sites
                ),
                http=http,
                normalizer=normalizer,
            )
        )
    if settings.workday_tenants:
        sources.append(
            WorkdayJobSource(
                tuple(
                    WorkdayTenant(target.company, target.value)
                    for target in settings.workday_tenants
                ),
                http=http,
                normalizer=normalizer,
            )
        )
    if settings.career_pages:
        sources.append(
            CareerPageJobSource(
                tuple(
                    CareerPage(target.company, target.value)
                    for target in settings.career_pages
                ),
                http=http,
                normalizer=normalizer,
                browser_loader=browser_loader,
            )
        )
    return tuple(sources)
