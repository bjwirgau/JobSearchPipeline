"""Coordinate discovery, validation, and persistence of Greenhouse companies."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from urllib.parse import unquote, urlsplit

from models import (
    CompanyProspect,
    CrawlPage,
    CrawlPageType,
    CrawlStatus,
)
from repositories import CompanyProspectRepository, CrawlPageRepository
from services.greenhouse_company_discovery import (
    CompanyDiscoveryError,
    GreenhouseBoardCandidate,
    GreenhouseBoardLookup,
    GreenhouseCompanyDiscovery,
)
from services.http_service import HttpRequestError
from utils.dates import utc_now


LOGGER = logging.getLogger(__name__)


class CompanyCrawlerDisabledError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CompanyCrawlFailure:
    board_token: str
    message: str


@dataclass(frozen=True, slots=True)
class CompanyCrawlResult:
    discovered_count: int
    new_count: int
    known_count: int
    retry_ready_count: int
    retry_deferred_count: int
    checked_count: int
    retried_count: int
    inserted_count: int
    companies: tuple[CompanyProspect, ...]
    failures: tuple[CompanyCrawlFailure, ...]
    discovery_warning: str | None = None


class GreenhouseCompanyCrawler:
    def __init__(
        self,
        *,
        discovery: GreenhouseCompanyDiscovery,
        boards: GreenhouseBoardLookup,
        repository: CompanyProspectRepository,
        crawl_pages: CrawlPageRepository,
        enabled: bool = False,
        concurrency: int = 5,
        failed_retry_after: timedelta = timedelta(days=1),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= concurrency <= 20:
            raise ValueError("company crawler concurrency must be between 1 and 20")
        if failed_retry_after.total_seconds() <= 0:
            raise ValueError("company crawler failed retry must be greater than zero")
        self._discovery = discovery
        self._boards = boards
        self._repository = repository
        self._crawl_pages = crawl_pages
        self._enabled = enabled
        self._concurrency = concurrency
        self._failed_retry_after = failed_retry_after
        self._clock = clock

    async def crawl(self, *, limit: int = 100) -> CompanyCrawlResult:
        if not self._enabled:
            raise CompanyCrawlerDisabledError(
                "company crawling is disabled; set "
                "JOB_AGENT_COMPANY_CRAWLER_ENABLED=true"
            )
        if not 1 <= limit <= 1_000:
            raise ValueError("company crawl limit must be between 1 and 1000")

        crawled_at = self._clock()
        known_urls = self._repository.known_company_urls()
        attempts = self._crawl_pages.list_for_source(
            source="greenhouse",
            page_type=CrawlPageType.COMPANY_BOARD,
        )
        adjusted_attempts = tuple(
            replace(
                attempt,
                next_crawl_at=attempt.last_crawled_at + self._failed_retry_after,
            )
            for attempt in attempts
            if attempt.crawl_status is CrawlStatus.FAILED
            and attempt.next_crawl_at
            != attempt.last_crawled_at + self._failed_retry_after
        )
        if adjusted_attempts:
            self._crawl_pages.save_all(adjusted_attempts)
            adjustments_by_url = {
                attempt.page_url: attempt for attempt in adjusted_attempts
            }
            attempts = tuple(
                adjustments_by_url.get(attempt.page_url, attempt)
                for attempt in attempts
            )
        attempts_by_url = {attempt.page_url: attempt for attempt in attempts}

        discovery_warning: str | None = None
        try:
            candidates = await self._discovery.discover()
        except (CompanyDiscoveryError, HttpRequestError) as error:
            if not known_urls and not attempts:
                raise
            candidates = ()
            failed_attempt_count = sum(
                attempt.crawl_status is CrawlStatus.FAILED
                for attempt in attempts
            )
            discovery_warning = (
                f"Live discovery unavailable ({error}); continuing with "
                f"{failed_attempt_count} stored failed board retries; "
                "successful known boards will not be revisited"
            )
            LOGGER.warning(discovery_warning)

        new_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.company_url not in known_urls
            and candidate.company_url not in attempts_by_url
        )
        known_count = sum(
            1
            for candidate in candidates
            if candidate.company_url in known_urls
            or (
                (attempt := attempts_by_url.get(candidate.company_url)) is not None
                and attempt.crawl_status is CrawlStatus.SUCCESS
            )
        )
        failed_attempts = tuple(
            attempt
            for attempt in attempts
            if attempt.crawl_status is CrawlStatus.FAILED
            and attempt.page_url not in known_urls
        )
        retry_ready = tuple(
            attempt
            for attempt in failed_attempts
            if attempt.next_crawl_at <= crawled_at
        )
        retry_deferred = tuple(
            attempt
            for attempt in failed_attempts
            if attempt.next_crawl_at > crawled_at
        )
        retry_candidates = tuple(
            (attempt, candidate)
            for attempt in retry_ready
            if (candidate := _candidate_from_crawl_page(attempt)) is not None
        )
        ordered_new = tuple(
            sorted(
                new_candidates,
                key=lambda candidate: (candidate.board_token, candidate.company_url),
            )
        )
        ordered_retries = tuple(
            candidate
            for _, candidate in sorted(
                retry_candidates,
                key=lambda item: (
                    item[0].next_crawl_at,
                    item[1].board_token,
                    item[1].company_url,
                ),
            )
        )
        selected = tuple((*ordered_new, *ordered_retries)[:limit])
        retry_urls = {candidate.company_url for candidate in ordered_retries}
        retried_count = sum(
            candidate.company_url in retry_urls for candidate in selected
        )
        outcomes = await self._retrieve_companies(selected)
        companies: list[CompanyProspect] = []
        failures: list[CompanyCrawlFailure] = []
        crawl_pages: list[CrawlPage] = []
        for candidate, outcome in zip(selected, outcomes):
            if isinstance(outcome, BaseException):
                if not isinstance(outcome, Exception):
                    raise outcome
                message = str(outcome)
                failures.append(
                    CompanyCrawlFailure(
                        board_token=candidate.board_token,
                        message=message,
                    )
                )
                crawl_status = CrawlStatus.FAILED
            else:
                companies.append(outcome)
                message = None
                crawl_status = CrawlStatus.SUCCESS
            crawl_pages.append(
                CrawlPage.from_attempt(
                    page_url=candidate.company_url,
                    source="greenhouse",
                    page_type=CrawlPageType.COMPANY_BOARD,
                    crawl_status=crawl_status,
                    crawled_at=crawled_at,
                    revisit_after=self._failed_retry_after,
                    last_error=message,
                )
            )

        self._repository.save_all(companies)
        self._crawl_pages.save_all(crawl_pages)
        return CompanyCrawlResult(
            discovered_count=len(candidates),
            new_count=len(new_candidates),
            known_count=known_count,
            retry_ready_count=len(retry_candidates),
            retry_deferred_count=len(retry_deferred),
            checked_count=len(selected),
            retried_count=retried_count,
            inserted_count=len(companies),
            companies=tuple(companies),
            failures=tuple(failures),
            discovery_warning=discovery_warning,
        )

    async def _retrieve_companies(
        self,
        candidates: tuple[GreenhouseBoardCandidate, ...],
    ) -> tuple[CompanyProspect | BaseException, ...]:
        semaphore = asyncio.Semaphore(self._concurrency)

        async def retrieve(
            candidate: GreenhouseBoardCandidate,
        ) -> CompanyProspect:
            async with semaphore:
                return await self._boards.retrieve(candidate)

        return tuple(
            await asyncio.gather(
                *(retrieve(candidate) for candidate in candidates),
                return_exceptions=True,
            )
        )


def _candidate_from_crawl_page(
    page: CrawlPage,
) -> GreenhouseBoardCandidate | None:
    path_parts = tuple(part for part in urlsplit(page.page_url).path.split("/") if part)
    if not path_parts:
        return None
    board_token = unquote(path_parts[0]).strip().casefold()
    if not board_token:
        return None
    return GreenhouseBoardCandidate(
        board_token=board_token,
        company_url=page.page_url,
    )
