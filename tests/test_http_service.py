"""HTTP throttling tests for polite crawler request pacing."""

from __future__ import annotations

import asyncio
import unittest
from typing import Mapping

from services import HttpResponse, ThrottledHttpClient


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)
        await asyncio.sleep(0)


class RecordingHttpClient:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.starts: list[tuple[str, str, float]] = []
        self.active_requests = 0
        self.maximum_active_requests = 0
        self.fail_urls: set[str] = set()

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return await self._request("GET", url)

    async def post_json(
        self,
        url: str,
        payload: Mapping[str, object],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        return await self._request("POST", url)

    async def _request(self, method: str, url: str) -> HttpResponse:
        self.starts.append((method, url, self.clock()))
        self.active_requests += 1
        self.maximum_active_requests = max(
            self.maximum_active_requests,
            self.active_requests,
        )
        await asyncio.sleep(0)
        self.clock.advance(0.25)
        self.active_requests -= 1
        if url in self.fail_urls:
            raise RuntimeError("request failed")
        return HttpResponse(200, url, "{}", {})


class ThrottledHttpClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_serializes_every_method_with_an_idle_interval(self) -> None:
        clock = FakeClock()
        delegate = RecordingHttpClient(clock)
        http = ThrottledHttpClient(
            http=delegate,
            interval_seconds=2,
            sleep_func=clock.sleep,
            clock=clock,
        )

        await http.get("https://example.com/one")
        await asyncio.gather(
            http.get("https://example.com/two"),
            http.post_json("https://example.com/three", {"ok": True}),
        )

        self.assertEqual(
            delegate.starts,
            [
                ("GET", "https://example.com/one", 0.0),
                ("GET", "https://example.com/two", 2.25),
                ("POST", "https://example.com/three", 4.5),
            ],
        )
        self.assertEqual(clock.sleeps, [2.0, 2.0])
        self.assertEqual(delegate.maximum_active_requests, 1)

    async def test_failure_still_delays_the_next_request(self) -> None:
        clock = FakeClock()
        delegate = RecordingHttpClient(clock)
        delegate.fail_urls.add("https://example.com/fail")
        http = ThrottledHttpClient(
            http=delegate,
            interval_seconds=1.5,
            sleep_func=clock.sleep,
            clock=clock,
        )

        with self.assertRaisesRegex(RuntimeError, "request failed"):
            await http.get("https://example.com/fail")
        await http.get("https://example.com/recovery")

        self.assertEqual(clock.sleeps, [1.5])
        self.assertEqual(delegate.starts[-1][2], 1.75)

    def test_rejects_an_invalid_interval(self) -> None:
        clock = FakeClock()
        with self.assertRaisesRegex(ValueError, "between 0 and 60"):
            ThrottledHttpClient(
                http=RecordingHttpClient(clock),
                interval_seconds=61,
            )


if __name__ == "__main__":
    unittest.main()
