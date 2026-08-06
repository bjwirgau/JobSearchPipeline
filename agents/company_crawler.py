"""Coordinate discovery, validation, and persistence of Greenhouse companies."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from models import (
    CompanyProspect,
    CrawlPage,
    CrawlPageType,
    CrawlStatus,
)
from repositories import CompanyProspectRepository, CrawlPageRepository
from services.greenhouse_company_discovery import (
    GreenhouseBoardCandidate,
    GreenhouseBoardLookup,
    GreenhouseCompanyDiscovery,
)
from utils.dates import utc_now


class CompanyCrawlerDisabledError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CompanyCrawlFailure:
    board_token: str
    message: str


@dataclass(frozen=True, slots=True)
class CompanyCrawlResult:
    discovered_count: int
    checked_count: int
    skipped_recent_count: int
    inserted_count: int
    updated_count: int
    companies: tuple[CompanyProspect, ...]
    failures: tuple[CompanyCrawlFailure, ...]


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
        revisit_after: timedelta = timedelta(days=7),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not 1 <= concurrency <= 20:
            raise ValueError("company crawler concurrency must be between 1 and 20")
        if revisit_after.total_seconds() <= 0:
            raise ValueError("company crawler revisit interval must be greater than zero")
        self._discovery = discovery
        self._boards = boards
        self._repository = repository
        self._crawl_pages = crawl_pages
        self._enabled = enabled
        self._concurrency = concurrency
        self._revisit_after = revisit_after
        self._clock = clock

    async def crawl(self, *, limit: int = 100) -> CompanyCrawlResult:
        if not self._enabled:
            raise CompanyCrawlerDisabledError(
                "company crawling is disabled; set "
                "JOB_AGENT_COMPANY_CRAWLER_ENABLED=true"
            )
        if not 1 <= limit <= 1_000:
            raise ValueError("company crawl limit must be between 1 and 1000")

        candidates = await self._discovery.discover()
        blocked_urls = self._crawl_pages.blocked_urls(
            source="greenhouse",
            page_type=CrawlPageType.COMPANY_BOARD,
            as_of=self._clock(),
        )
        eligible = tuple(
            candidate
            for candidate in candidates
            if candidate.company_url not in blocked_urls
        )
        known_urls = self._repository.known_company_urls()
        ordered = sorted(
            eligible,
            key=lambda candidate: (
                candidate.company_url in known_urls,
                candidate.board_token,
                candidate.company_url,
            ),
        )
        selected = tuple(ordered[:limit])
        outcomes = await self._retrieve_companies(selected)
        companies: list[CompanyProspect] = []
        failures: list[CompanyCrawlFailure] = []
        crawl_pages: list[CrawlPage] = []
        crawled_at = self._clock()
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
                    revisit_after=self._revisit_after,
                    last_error=message,
                )
            )

        self._repository.save_all(companies)
        self._crawl_pages.save_all(crawl_pages)
        inserted_count = sum(
            company.company_url not in known_urls for company in companies
        )
        return CompanyCrawlResult(
            discovered_count=len(candidates),
            checked_count=len(selected),
            skipped_recent_count=len(candidates) - len(eligible),
            inserted_count=inserted_count,
            updated_count=len(companies) - inserted_count,
            companies=tuple(companies),
            failures=tuple(failures),
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
