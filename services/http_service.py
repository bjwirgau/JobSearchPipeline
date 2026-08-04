"""Small asynchronous HTTP boundary backed by Requests when installed."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import urlsplit


class HttpRequestError(RuntimeError):
    pass


class MissingHttpDependencyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    url: str
    text: str
    headers: Mapping[str, str]

    def json(self) -> Any:
        try:
            return json.loads(self.text)
        except json.JSONDecodeError as error:
            raise HttpRequestError(f"invalid JSON response from {self.url}") from error


class HttpClient(Protocol):
    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Perform an HTTP GET request."""

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        """Perform an HTTP POST with a JSON request body."""


class RequestsHttpClient:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return await asyncio.to_thread(
            self._request,
            "GET",
            url,
            params=params,
            headers=headers,
        )

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return await asyncio.to_thread(
            self._request,
            "POST",
            url,
            json_body=payload,
            headers=headers,
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        json_body: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        if urlsplit(url).scheme not in {"http", "https"}:
            raise HttpRequestError(f"unsupported URL scheme: {url}")
        try:
            import requests
        except ImportError as error:
            raise MissingHttpDependencyError(
                "install live-search dependencies with: pip install -e '.[search]'"
            ) from error
        request_headers = {"User-Agent": self._user_agent, **dict(headers or {})}
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=request_headers,
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise HttpRequestError(f"{method} {url} failed: {error}") from error
        return HttpResponse(
            status_code=response.status_code,
            url=response.url,
            text=response.text,
            headers=dict(response.headers),
        )
