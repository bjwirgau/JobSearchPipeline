"""Greenhouse company discovery and crawler tests."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from typing import Mapping

from agents import CompanyCrawlerDisabledError, GreenhouseCompanyCrawler
from database import Database, MySQLConfig, initialize_schema
from models import CompanyProspect
from repositories import CompanyProspectRepository, CrawlPageRepository
from services import (
    CompanyDiscoveryError,
    GreenhouseBoardCandidate,
    GreenhouseCdxDiscovery,
    GreenhousePublicBoardLookup,
    HttpResponse,
)
from services.http_service import HttpRequestError
from tests.mysql_fakes import FakeMySQLServer


class FakeDiscoveryHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, object] | None]] = []

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        self.calls.append((url, params))
        if url.endswith("collinfo.json"):
            payload: object = [
                {
                    "id": "CC-MAIN-2026-30",
                    "cdx-api": (
                        "https://index.commoncrawl.org/"
                        "CC-MAIN-2026-30-index"
                    ),
                }
            ]
            text = json.dumps(payload)
        else:
            host = str(params["url"]).removesuffix("/*")
            urls = {
                "job-boards.greenhouse.io": (
                    "https://job-boards.greenhouse.io/example/jobs/123",
                    "https://job-boards.greenhouse.io/jobs/123",
                ),
                "boards.greenhouse.io": (
                    "https://boards.greenhouse.io/example/jobs/456",
                ),
            }[host]
            text = "\n".join(json.dumps({"url": item}) for item in urls)
        return HttpResponse(200, url, text, {"Content-Type": "application/json"})

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        raise AssertionError("company discovery must use GET")


class FakeBoardHttpClient(FakeDiscoveryHttpClient):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        self.calls.append((url, params))
        return HttpResponse(
            200,
            url,
            json.dumps({"name": "Example Company", "content": ""}),
            {"Content-Type": "application/json"},
        )


class FakeFallbackDiscoveryHttpClient(FakeDiscoveryHttpClient):
    def __init__(self, *, failed_archive_hosts: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.failed_archive_hosts = failed_archive_hosts

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        self.calls.append((url, params))
        if url.endswith("collinfo.json"):
            return HttpResponse(
                200,
                url,
                json.dumps(
                    [
                        {
                            "cdx-api": (
                                "https://index.commoncrawl.org/"
                                "CC-MAIN-2026-30-index"
                            )
                        }
                    ]
                ),
                {"Content-Type": "application/json"},
            )
        if url.startswith("https://index.commoncrawl.org/"):
            raise HttpRequestError("Common Crawl returned 504")

        host = str(params["url"]).removesuffix("/*")
        if host in self.failed_archive_hosts:
            raise HttpRequestError("Internet Archive returned 503")
        urls = {
            "job-boards.greenhouse.io": (
                "https://job-boards.greenhouse.io/example",
            ),
            "boards.greenhouse.io": (),
        }[host]
        payload: list[list[str]] = [["original"]]
        payload.extend([[item] for item in urls])
        return HttpResponse(
            200,
            url,
            json.dumps(payload),
            {"Content-Type": "application/json"},
        )


class FakeCommonCrawlFallbackHttpClient(FakeDiscoveryHttpClient):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if url == GreenhouseCdxDiscovery.INTERNET_ARCHIVE_INDEX_URL:
            self.calls.append((url, params))
            raise HttpRequestError("Internet Archive returned 503")
        return await super().get(url, params=params, headers=headers)


class FakeRetryArchiveHttpClient(FakeFallbackDiscoveryHttpClient):
    def __init__(self) -> None:
        super().__init__()
        self.failed_once = False

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if (
            url == GreenhouseCdxDiscovery.INTERNET_ARCHIVE_INDEX_URL
            and not self.failed_once
        ):
            self.failed_once = True
            self.calls.append((url, params))
            raise HttpRequestError("Internet Archive timed out")
        return await super().get(url, params=params, headers=headers)


class FakeRetryCommonCrawlHttpClient(FakeCommonCrawlFallbackHttpClient):
    def __init__(self) -> None:
        super().__init__()
        self.common_crawl_failed_once = False

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if url.endswith("collinfo.json") and not self.common_crawl_failed_once:
            self.common_crawl_failed_once = True
            self.calls.append((url, params))
            raise HttpRequestError("Common Crawl disconnected")
        return await super().get(url, params=params, headers=headers)


class StaticDiscovery:
    def __init__(self, candidates: tuple[GreenhouseBoardCandidate, ...]) -> None:
        self.candidates = candidates

    async def discover(self) -> tuple[GreenhouseBoardCandidate, ...]:
        return self.candidates


class FailingDiscovery:
    async def discover(self) -> tuple[GreenhouseBoardCandidate, ...]:
        raise CompanyDiscoveryError("public indexes unavailable")


class StaticBoardLookup:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def retrieve(
        self,
        candidate: GreenhouseBoardCandidate,
    ) -> CompanyProspect:
        self.calls.append(candidate.board_token)
        if candidate.board_token == "broken":
            raise RuntimeError("board not found")
        return CompanyProspect.from_board(
            company_name=f"{candidate.board_token.title()} Company",
            board_token=candidate.board_token,
            company_url=candidate.company_url,
        )


class CompanyCrawlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        database = Database(
            MySQLConfig(),
            connect_factory=FakeMySQLServer().connect,
        )
        initialize_schema(database)
        self.repository = CompanyProspectRepository(database)
        self.crawl_pages = CrawlPageRepository(database)

    async def test_archive_discovers_and_deduplicates_us_boards(self) -> None:
        http = FakeDiscoveryHttpClient()
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=500,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            candidates,
            (
                GreenhouseBoardCandidate(
                    board_token="example",
                    company_url="https://job-boards.greenhouse.io/example",
                ),
            ),
        )
        self.assertEqual(len(http.calls), 2)
        self.assertTrue(
            all(call[1]["limit"] == 500 for call in http.calls)
        )

    async def test_primary_archive_avoids_unhealthy_common_crawl(self) -> None:
        http = FakeFallbackDiscoveryHttpClient()
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=100,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            candidates,
            (
                GreenhouseBoardCandidate(
                    board_token="example",
                    company_url="https://job-boards.greenhouse.io/example",
                ),
            ),
        )
        archive_calls = [
            call
            for call in http.calls
            if call[0] == discovery.INTERNET_ARCHIVE_INDEX_URL
        ]
        self.assertEqual(len(archive_calls), 2)
        self.assertTrue(
            all("[^/?]+" in call[1]["filter"] for call in archive_calls)
        )
        self.assertTrue(
            all(
                call[1]["page"] == 0 and call[1]["pageSize"] == 1
                for call in archive_calls
            )
        )
        self.assertFalse(
            any(
                call[0].startswith("https://index.commoncrawl.org/")
                for call in http.calls
            )
        )

    async def test_common_crawl_is_used_when_archive_is_unavailable(self) -> None:
        http = FakeCommonCrawlFallbackHttpClient()
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=100,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            {candidate.board_token for candidate in candidates},
            {"example"},
        )
        self.assertEqual(
            sum(
                call[0] == discovery.INTERNET_ARCHIVE_INDEX_URL
                for call in http.calls
            ),
            4,
        )
        self.assertTrue(
            any(call[0].endswith("collinfo.json") for call in http.calls)
        )

    async def test_archive_request_retries_once_after_http_failure(self) -> None:
        http = FakeRetryArchiveHttpClient()
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=100,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            {candidate.board_token for candidate in candidates},
            {"example"},
        )
        self.assertEqual(
            sum(
                call[0] == discovery.INTERNET_ARCHIVE_INDEX_URL
                for call in http.calls
            ),
            3,
        )

    async def test_common_crawl_request_retries_after_disconnect(self) -> None:
        http = FakeRetryCommonCrawlHttpClient()
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=100,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            {candidate.board_token for candidate in candidates},
            {"example"},
        )
        self.assertEqual(
            sum(call[0].endswith("collinfo.json") for call in http.calls),
            2,
        )

    async def test_fallback_keeps_results_when_one_archive_host_fails(self) -> None:
        http = FakeFallbackDiscoveryHttpClient(
            failed_archive_hosts=("boards.greenhouse.io",)
        )
        discovery = GreenhouseCdxDiscovery(
            http=http,
            scan_limit=100,
            request_delay_seconds=0,
        )

        candidates = await discovery.discover()

        self.assertEqual(
            {candidate.board_token for candidate in candidates},
            {"example"},
        )

    async def test_greenhouse_lookup_uses_public_board_metadata(self) -> None:
        http = FakeBoardHttpClient()
        lookup = GreenhousePublicBoardLookup(http=http)
        candidate = GreenhouseBoardCandidate(
            board_token="example",
            company_url="https://job-boards.greenhouse.io/example",
        )

        company = await lookup.retrieve(candidate)

        self.assertEqual(company.company_name, "Example Company")
        self.assertEqual(
            http.calls[0][0],
            "https://boards-api.greenhouse.io/v1/boards/example",
        )

    async def test_crawler_prioritizes_and_inserts_new_companies(self) -> None:
        existing = CompanyProspect.from_board(
            company_name="Existing Company",
            board_token="existing",
            company_url="https://job-boards.greenhouse.io/existing",
        )
        self.repository.save(existing)
        candidates = (
            GreenhouseBoardCandidate("existing", existing.company_url),
            GreenhouseBoardCandidate(
                "new",
                "https://job-boards.greenhouse.io/new",
            ),
            GreenhouseBoardCandidate(
                "broken",
                "https://job-boards.greenhouse.io/broken",
            ),
        )
        boards = StaticBoardLookup()
        crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery(candidates),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            concurrency=2,
        )

        result = await crawler.crawl(limit=3)

        self.assertEqual(result.discovered_count, 3)
        self.assertEqual(result.new_count, 2)
        self.assertEqual(result.known_count, 1)
        self.assertEqual(result.checked_count, 2)
        self.assertEqual(result.retry_ready_count, 0)
        self.assertEqual(result.retry_deferred_count, 0)
        self.assertEqual(result.retried_count, 0)
        self.assertEqual(result.inserted_count, 1)
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].board_token, "broken")
        self.assertEqual(len(self.repository.list_all()), 2)
        self.assertEqual(len(boards.calls), 2)
        self.assertNotIn("existing", boards.calls)
        failed_page = self.crawl_pages.get(
            "https://job-boards.greenhouse.io/broken"
        )
        self.assertEqual(failed_page.crawl_status.value, "failed")

    async def test_successful_known_board_is_never_revisited(self) -> None:
        now = [datetime(2026, 8, 6, 12, tzinfo=timezone.utc)]
        candidate = GreenhouseBoardCandidate(
            "example",
            "https://job-boards.greenhouse.io/example",
        )
        boards = StaticBoardLookup()
        initial_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((candidate,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(days=7),
            clock=lambda: now[0],
        )
        retry_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((candidate,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )

        first = await initial_crawler.crawl()
        second = await retry_crawler.crawl()
        now[0] += timedelta(hours=25)
        third = await retry_crawler.crawl()

        self.assertEqual(first.checked_count, 1)
        self.assertEqual(second.checked_count, 0)
        self.assertEqual(second.known_count, 1)
        self.assertEqual(third.checked_count, 0)
        self.assertEqual(third.known_count, 1)
        self.assertEqual(boards.calls, ["example"])

    async def test_failed_board_retries_after_shorter_cooldown(self) -> None:
        now = [datetime(2026, 8, 6, 12, tzinfo=timezone.utc)]
        candidate = GreenhouseBoardCandidate(
            "broken",
            "https://job-boards.greenhouse.io/broken",
        )
        boards = StaticBoardLookup()
        initial_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((candidate,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(days=7),
            clock=lambda: now[0],
        )
        retry_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((candidate,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )

        first = await initial_crawler.crawl()
        second = await retry_crawler.crawl()
        rescheduled = self.crawl_pages.get(candidate.company_url)
        now[0] += timedelta(hours=25)
        third = await retry_crawler.crawl()

        self.assertEqual(first.new_count, 1)
        self.assertEqual(first.checked_count, 1)
        self.assertEqual(second.checked_count, 0)
        self.assertEqual(second.retry_deferred_count, 1)
        self.assertEqual(
            rescheduled.next_crawl_at,
            datetime(2026, 8, 7, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(third.retry_ready_count, 1)
        self.assertEqual(third.checked_count, 1)
        self.assertEqual(third.retried_count, 1)
        self.assertEqual(boards.calls, ["broken", "broken"])

    async def test_new_boards_are_checked_before_ready_retries(self) -> None:
        now = [datetime(2026, 8, 6, 12, tzinfo=timezone.utc)]
        broken = GreenhouseBoardCandidate(
            "broken",
            "https://job-boards.greenhouse.io/broken",
        )
        new = GreenhouseBoardCandidate(
            "new",
            "https://job-boards.greenhouse.io/new",
        )
        boards = StaticBoardLookup()
        first_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((broken,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )
        await first_crawler.crawl()
        now[0] += timedelta(hours=25)
        second_crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((new,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )

        result = await second_crawler.crawl(limit=1)

        self.assertEqual(result.new_count, 1)
        self.assertEqual(result.retry_ready_count, 1)
        self.assertEqual(result.checked_count, 1)
        self.assertEqual(result.retried_count, 0)
        self.assertEqual(boards.calls, ["broken", "new"])

    async def test_crawler_uses_stored_us_boards_when_discovery_is_down(self) -> None:
        existing = CompanyProspect.from_board(
            company_name="Existing Company",
            board_token="existing",
            company_url="https://job-boards.greenhouse.io/existing",
        )
        self.repository.save(existing)
        boards = StaticBoardLookup()
        crawler = GreenhouseCompanyCrawler(
            discovery=FailingDiscovery(),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
        )

        with self.assertLogs("agents.company_crawler", level="WARNING"):
            result = await crawler.crawl()

        self.assertEqual(result.discovered_count, 0)
        self.assertEqual(result.checked_count, 0)
        self.assertEqual(result.inserted_count, 0)
        self.assertEqual(boards.calls, [])
        self.assertIsNotNone(result.discovery_warning)
        self.assertIn(
            "successful known boards will not be revisited",
            result.discovery_warning or "",
        )

    async def test_crawler_retries_stored_failure_when_discovery_is_down(self) -> None:
        now = [datetime(2026, 8, 6, 12, tzinfo=timezone.utc)]
        broken = GreenhouseBoardCandidate(
            "broken",
            "https://job-boards.greenhouse.io/broken",
        )
        boards = StaticBoardLookup()
        crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery((broken,)),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )
        await crawler.crawl()
        now[0] += timedelta(hours=25)
        retry_crawler = GreenhouseCompanyCrawler(
            discovery=FailingDiscovery(),
            boards=boards,
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
            failed_retry_after=timedelta(hours=24),
            clock=lambda: now[0],
        )

        with self.assertLogs("agents.company_crawler", level="WARNING"):
            result = await retry_crawler.crawl()

        self.assertEqual(result.discovered_count, 0)
        self.assertEqual(result.retry_ready_count, 1)
        self.assertEqual(result.checked_count, 1)
        self.assertEqual(result.retried_count, 1)
        self.assertEqual(boards.calls, ["broken", "broken"])

    async def test_crawler_fails_when_discovery_and_inventory_are_empty(self) -> None:
        crawler = GreenhouseCompanyCrawler(
            discovery=FailingDiscovery(),
            boards=StaticBoardLookup(),
            repository=self.repository,
            crawl_pages=self.crawl_pages,
            enabled=True,
        )

        with self.assertRaisesRegex(
            CompanyDiscoveryError,
            "public indexes unavailable",
        ):
            await crawler.crawl()

    async def test_crawler_is_disabled_by_default(self) -> None:
        crawler = GreenhouseCompanyCrawler(
            discovery=StaticDiscovery(()),
            boards=StaticBoardLookup(),
            repository=self.repository,
            crawl_pages=self.crawl_pages,
        )

        with self.assertRaisesRegex(
            CompanyCrawlerDisabledError,
            "JOB_AGENT_COMPANY_CRAWLER_ENABLED",
        ):
            await crawler.crawl()


if __name__ == "__main__":
    unittest.main()
