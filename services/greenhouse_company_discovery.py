"""Discover Greenhouse board tokens and validate them against the public API."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import quote, unquote, urlsplit

from models import CompanyProspect, CrawlDiscoveryCursor

from .http_service import HttpClient, HttpRequestError, HttpResponse


LOGGER = logging.getLogger(__name__)


class CompanyDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GreenhouseBoardCandidate:
    board_token: str
    company_url: str


class GreenhouseCompanyDiscovery(Protocol):
    async def discover(
        self,
        *,
        excluded_urls: frozenset[str] = frozenset(),
    ) -> tuple[GreenhouseBoardCandidate, ...]:
        """Return unique Greenhouse board candidates."""


class GreenhouseBoardLookup(Protocol):
    async def retrieve(
        self,
        candidate: GreenhouseBoardCandidate,
    ) -> CompanyProspect:
        """Validate a board candidate and retrieve its company name."""


class CrawlDiscoveryCursorStore(Protocol):
    def get(
        self,
        *,
        provider: str,
        scope: str,
    ) -> CrawlDiscoveryCursor | None:
        """Load the next page for a provider scope."""

    def save(self, cursor_state: CrawlDiscoveryCursor) -> None:
        """Persist the next page for a provider scope."""


class GreenhouseCdxDiscovery:
    COLLECTIONS_URL = "https://index.commoncrawl.org/collinfo.json"
    INTERNET_ARCHIVE_INDEX_URL = "https://web.archive.org/cdx/search/cdx"
    ARCHIVE_REQUEST_ATTEMPTS = 2
    COMMON_CRAWL_REQUEST_ATTEMPTS = 3
    BOARD_HOSTS = (
        "job-boards.greenhouse.io",
        "boards.greenhouse.io",
    )

    def __init__(
        self,
        *,
        http: HttpClient,
        cursors: CrawlDiscoveryCursorStore | None = None,
        scan_limit: int = 5_000,
        request_delay_seconds: float = 1.0,
    ) -> None:
        if not 1 <= scan_limit <= 100_000:
            raise ValueError("company crawler scan limit must be between 1 and 100000")
        if not 0 <= request_delay_seconds <= 60:
            raise ValueError(
                "company crawler request delay must be between 0 and 60 seconds"
            )
        self._http = http
        self._cursors = cursors
        self._scan_limit = scan_limit
        self._request_delay_seconds = request_delay_seconds

    async def discover(
        self,
        *,
        excluded_urls: frozenset[str] = frozenset(),
    ) -> tuple[GreenhouseBoardCandidate, ...]:
        archive_candidates: tuple[GreenhouseBoardCandidate, ...] = ()
        archive_error: CompanyDiscoveryError | None = None
        try:
            archive_candidates = await self._discover_from_internet_archive()
        except CompanyDiscoveryError as error:
            archive_error = error
            LOGGER.warning(
                "Internet Archive discovery failed; using Common Crawl: %s",
                error,
            )
        else:
            unseen_archive_candidates = tuple(
                candidate
                for candidate in archive_candidates
                if candidate.company_url not in excluded_urls
            )
            if unseen_archive_candidates:
                LOGGER.info(
                    "Internet Archive page returned %d candidates (%d unseen)",
                    len(archive_candidates),
                    len(unseen_archive_candidates),
                )
                return archive_candidates
            LOGGER.info(
                "Internet Archive page returned no unseen boards; "
                "supplementing it with Common Crawl"
            )

        try:
            common_crawl_candidates = await self._discover_from_common_crawl()
        except (CompanyDiscoveryError, HttpRequestError) as common_crawl_error:
            if archive_candidates:
                LOGGER.warning(
                    "Common Crawl supplemental discovery failed; retaining "
                    "Internet Archive candidates: %s",
                    common_crawl_error,
                )
                return archive_candidates
            raise CompanyDiscoveryError(
                "Greenhouse discovery failed through both Internet Archive "
                f"({archive_error}) and Common Crawl ({common_crawl_error})"
            ) from common_crawl_error

        candidates = {
            candidate.company_url: candidate
            for candidate in (*archive_candidates, *common_crawl_candidates)
        }
        LOGGER.info(
            "Greenhouse discovery returned %d merged candidates "
            "(%d Internet Archive, %d Common Crawl)",
            len(candidates),
            len(archive_candidates),
            len(common_crawl_candidates),
        )
        return _sorted_candidates(candidates)

    async def _discover_from_common_crawl(
        self,
    ) -> tuple[GreenhouseBoardCandidate, ...]:
        index_url = await self._latest_index_url()
        candidates: dict[str, GreenhouseBoardCandidate] = {}
        failures: list[tuple[str, HttpRequestError]] = []
        for host in self.BOARD_HOSTS:
            await self._delay_request()
            scope = f"{urlsplit(index_url).path.rsplit('/', 1)[-1]}:{host}"
            try:
                page, page_count = await self._current_page(
                    provider="common_crawl",
                    scope=scope,
                    page_count_loader=lambda: self._common_crawl_page_count(
                        index_url,
                        host,
                    ),
                )
                LOGGER.info(
                    "Scanning Common Crawl for %s on page %d of %d",
                    host,
                    page + 1,
                    page_count,
                )
                response = await self._request_common_crawl(
                    index_url,
                    params={
                        "url": f"{host}/*",
                        "output": "json",
                        "fl": "url",
                        "filter": "status:200",
                        "collapse": "urlkey",
                        "page": page,
                        "pageSize": 1,
                        "limit": self._scan_limit,
                    },
                )
            except HttpRequestError as error:
                failures.append((host, error))
                LOGGER.warning(
                    "Common Crawl discovery failed for %s: %s",
                    host,
                    error,
                )
                continue
            urls = _urls_from_cdx(response.text)
            self._advance_cursor(
                provider="common_crawl",
                scope=scope,
                page=page,
                page_count=page_count,
            )
            _collect_candidates(candidates, urls)
        if not candidates:
            failed_hosts = ", ".join(host for host, _ in failures)
            failure_detail = (
                f"; failed hosts: {failed_hosts}; last error: {failures[-1][1]}"
                if failures
                else ""
            )
            raise CompanyDiscoveryError(
                "Common Crawl did not return Greenhouse candidates"
                f"{failure_detail}"
            ) from (failures[-1][1] if failures else None)
        return _sorted_candidates(candidates)

    async def _discover_from_internet_archive(
        self,
    ) -> tuple[GreenhouseBoardCandidate, ...]:
        candidates: dict[str, GreenhouseBoardCandidate] = {}
        failures: list[tuple[str, HttpRequestError]] = []
        for host in self.BOARD_HOSTS:
            await self._delay_request()
            try:
                page, page_count = await self._current_page(
                    provider="internet_archive",
                    scope=host,
                    page_count_loader=lambda: self._internet_archive_page_count(
                        host
                    ),
                )
                LOGGER.info(
                    "Scanning Internet Archive for %s on page %d of %d",
                    host,
                    page + 1,
                    page_count,
                )
                response = await self._request_internet_archive(host, page=page)
            except HttpRequestError as error:
                failures.append((host, error))
                LOGGER.warning(
                    "Internet Archive discovery failed for %s: %s",
                    host,
                    error,
                )
                continue
            urls = _urls_from_cdx(response.text)
            self._advance_cursor(
                provider="internet_archive",
                scope=host,
                page=page,
                page_count=page_count,
            )
            _collect_candidates(candidates, urls)
        if not candidates:
            failed_hosts = ", ".join(host for host, _ in failures)
            failure_detail = (
                f"; failed hosts: {failed_hosts}" if failed_hosts else ""
            )
            raise CompanyDiscoveryError(
                "Internet Archive did not return Greenhouse candidates"
                f"{failure_detail}"
            ) from (failures[-1][1] if failures else None)
        return _sorted_candidates(candidates)

    async def _request_internet_archive(
        self,
        host: str,
        *,
        page: int,
    ) -> HttpResponse:
        params = self._internet_archive_params(host)
        params.update(
            {
                "output": "json",
                "fl": "original",
                "page": page,
                "limit": self._scan_limit,
            }
        )
        return await self._request_internet_archive_with_params(params)

    async def _internet_archive_page_count(self, host: str) -> int:
        params = self._internet_archive_params(host)
        params["showNumPages"] = "true"
        response = await self._request_internet_archive_with_params(params)
        return _page_count_from_cdx(response.text)

    def _internet_archive_params(self, host: str) -> dict[str, object]:
        return {
            "url": f"{host}/*",
            "filter": f"original:^https?://{re.escape(host)}/[^/?]+/?$",
            "collapse": "urlkey",
            "pageSize": 1,
        }

    async def _request_internet_archive_with_params(
        self,
        params: Mapping[str, object],
    ) -> HttpResponse:
        last_error: HttpRequestError | None = None
        for attempt in range(self.ARCHIVE_REQUEST_ATTEMPTS):
            if attempt and self._request_delay_seconds:
                await asyncio.sleep(self._request_delay_seconds)
            try:
                return await self._http.get(
                    self.INTERNET_ARCHIVE_INDEX_URL,
                    params=params,
                    headers={
                        "Accept-Encoding": "gzip",
                        "Connection": "close",
                    },
                )
            except HttpRequestError as error:
                last_error = error
        if last_error is None:
            raise RuntimeError("archive request attempts must be greater than zero")
        raise last_error

    async def _common_crawl_page_count(self, index_url: str, host: str) -> int:
        response = await self._request_common_crawl(
            index_url,
            params={
                "url": f"{host}/*",
                "filter": "status:200",
                "collapse": "urlkey",
                "showNumPages": "true",
                "pageSize": 1,
            },
        )
        return _page_count_from_cdx(response.text)

    async def _current_page(
        self,
        *,
        provider: str,
        scope: str,
        page_count_loader: Callable[[], Awaitable[int]],
    ) -> tuple[int, int]:
        if self._cursors is None:
            return 0, 1
        state = self._cursors.get(provider=provider, scope=scope)
        if state is not None and state.next_page != 0:
            return state.next_page, state.page_count
        try:
            page_count = await page_count_loader()
        except (CompanyDiscoveryError, HttpRequestError, ValueError) as error:
            if state is None:
                LOGGER.warning(
                    "Could not determine %s page count for %s; starting at "
                    "page 1: %s",
                    provider,
                    scope,
                    error,
                )
                return 0, 1
            LOGGER.warning(
                "Could not refresh %s page count for %s; retaining %d pages: %s",
                provider,
                scope,
                state.page_count,
                error,
            )
            page_count = state.page_count
        return 0, page_count

    def _advance_cursor(
        self,
        *,
        provider: str,
        scope: str,
        page: int,
        page_count: int,
    ) -> None:
        if self._cursors is None:
            return
        self._cursors.save(
            CrawlDiscoveryCursor(
                provider=provider,
                scope=scope,
                next_page=(page + 1) % page_count,
                page_count=page_count,
            )
        )

    async def _delay_request(self) -> None:
        if self._request_delay_seconds:
            await asyncio.sleep(self._request_delay_seconds)

    async def _latest_index_url(self) -> str:
        response = await self._request_common_crawl(self.COLLECTIONS_URL)
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise CompanyDiscoveryError(
                "Common Crawl did not return an index collection"
            )
        collection = payload[0]
        if not isinstance(collection, Mapping):
            raise CompanyDiscoveryError("Common Crawl collection is invalid")
        index_url = str(collection.get("cdx-api") or "").strip()
        if not index_url.startswith("https://index.commoncrawl.org/"):
            raise CompanyDiscoveryError("Common Crawl index URL is invalid")
        return index_url

    async def _request_common_crawl(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
    ) -> HttpResponse:
        last_error: HttpRequestError | None = None
        for attempt in range(self.COMMON_CRAWL_REQUEST_ATTEMPTS):
            if attempt and self._request_delay_seconds:
                await asyncio.sleep(self._request_delay_seconds)
            try:
                return await self._http.get(
                    url,
                    params=params,
                    headers={"Connection": "close"},
                )
            except HttpRequestError as error:
                last_error = error
        if last_error is None:
            raise RuntimeError(
                "Common Crawl request attempts must be greater than zero"
            )
        raise last_error


class GreenhousePublicBoardLookup:
    def __init__(self, *, http: HttpClient) -> None:
        self._http = http

    async def retrieve(
        self,
        candidate: GreenhouseBoardCandidate,
    ) -> CompanyProspect:
        token = quote(candidate.board_token, safe="")
        response = await self._http.get(
            f"https://boards-api.greenhouse.io/v1/boards/{token}"
        )
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise CompanyDiscoveryError(
                f"Greenhouse returned an invalid board for {candidate.board_token}"
            )
        company_name = str(payload.get("name") or "").strip()
        if not company_name:
            raise CompanyDiscoveryError(
                f"Greenhouse board {candidate.board_token} has no company name"
            )
        return CompanyProspect.from_board(
            company_name=company_name,
            board_token=candidate.board_token,
            company_url=candidate.company_url,
        )


def _urls_from_cdx(text: str) -> tuple[str, ...]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _urls_from_json_lines(text)
    if isinstance(payload, Mapping):
        url = str(payload.get("url") or payload.get("original") or "").strip()
        return (url,) if url else ()
    if isinstance(payload, list):
        return _urls_from_json_rows(payload)
    raise CompanyDiscoveryError("CDX service returned an invalid response")


def _page_count_from_cdx(text: str) -> int:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise CompanyDiscoveryError(
            "CDX service returned an invalid page count"
        ) from error
    if isinstance(payload, bool):
        page_count = 0
    elif isinstance(payload, int):
        page_count = payload
    elif isinstance(payload, Mapping):
        value = payload.get("pages")
        try:
            page_count = int(value) if isinstance(value, (int, str)) else 0
        except ValueError:
            page_count = 0
    else:
        page_count = 0
    if page_count < 1:
        raise CompanyDiscoveryError(
            "CDX service returned a non-positive page count"
        )
    return page_count


def _urls_from_json_lines(text: str) -> tuple[str, ...]:
    urls: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise CompanyDiscoveryError(
                "CDX service returned an invalid index record"
            ) from error
        if not isinstance(record, Mapping):
            raise CompanyDiscoveryError("CDX service returned an invalid index record")
        url = str(record.get("url") or record.get("original") or "").strip()
        if url:
            urls.append(url)
    return tuple(urls)


def _urls_from_json_rows(payload: list[object]) -> tuple[str, ...]:
    if not payload:
        return ()
    header = payload[0]
    if not isinstance(header, list):
        raise CompanyDiscoveryError("CDX service returned an invalid result header")
    fields = tuple(str(field) for field in header)
    field_name = "original" if "original" in fields else "url"
    if field_name not in fields:
        raise CompanyDiscoveryError("CDX result does not include a URL field")
    url_index = fields.index(field_name)
    urls: list[str] = []
    for row in payload[1:]:
        if not isinstance(row, list) or len(row) <= url_index:
            raise CompanyDiscoveryError("CDX service returned an invalid result row")
        url = str(row[url_index]).strip()
        if url:
            urls.append(url)
    return tuple(urls)


def _collect_candidates(
    candidates: dict[str, GreenhouseBoardCandidate],
    urls: tuple[str, ...],
) -> None:
    for url in urls:
        candidate = _candidate_from_url(url)
        if candidate is not None:
            candidates.setdefault(candidate.company_url, candidate)


def _sorted_candidates(
    candidates: Mapping[str, GreenhouseBoardCandidate],
) -> tuple[GreenhouseBoardCandidate, ...]:
    return tuple(
        sorted(
            candidates.values(),
            key=lambda candidate: (
                candidate.board_token,
                candidate.company_url,
            ),
        )
    )


def _candidate_from_url(url: str) -> GreenhouseBoardCandidate | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    if host not in GreenhouseCdxDiscovery.BOARD_HOSTS:
        return None
    path_parts = tuple(part for part in parts.path.split("/") if part)
    if not path_parts:
        return None
    board_token = unquote(path_parts[0]).strip().casefold()
    if not _valid_board_token(board_token):
        return None
    company_url = (
        "https://job-boards.greenhouse.io/"
        f"{quote(board_token, safe='-_.~')}"
    )
    return GreenhouseBoardCandidate(
        board_token=board_token,
        company_url=company_url,
    )


def _valid_board_token(value: str) -> bool:
    if not value or len(value) > 191:
        return False
    if value in {"embed", "job_application_requests", "jobs"}:
        return False
    return all(character.isalnum() or character in "-_." for character in value)


# Compatibility for code that imported the original implementation name.
CommonCrawlGreenhouseDiscovery = GreenhouseCdxDiscovery
