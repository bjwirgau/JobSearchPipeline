"""Optional dynamic-page loaders used only after an HTTP parse yields no jobs."""

from __future__ import annotations

import asyncio


class BrowserDependencyError(RuntimeError):
    pass


class PlaywrightPageLoader:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self._timeout_ms = int(timeout_seconds * 1000)
        self._user_agent = user_agent

    async def load(self, url: str) -> str:
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise BrowserDependencyError(
                "install browser dependencies with: pip install -e '.[browser]'"
            ) from error
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(user_agent=self._user_agent)
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                return await page.content()
            finally:
                await browser.close()


class SeleniumPageLoader:
    def __init__(self, *, timeout_seconds: float, user_agent: str) -> None:
        self._timeout_seconds = timeout_seconds
        self._user_agent = user_agent

    async def load(self, url: str) -> str:
        return await asyncio.to_thread(self._load_sync, url)

    def _load_sync(self, url: str) -> str:
        try:
            from selenium import webdriver
        except ImportError as error:
            raise BrowserDependencyError(
                "install browser dependencies with: pip install -e '.[browser]'"
            ) from error
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument(f"--user-agent={self._user_agent}")
        driver = webdriver.Chrome(options=options)
        try:
            driver.set_page_load_timeout(self._timeout_seconds)
            driver.get(url)
            return driver.page_source
        finally:
            driver.quit()
