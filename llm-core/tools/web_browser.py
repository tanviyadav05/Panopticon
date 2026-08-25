"""Playwright-based web browsing tool for the Researcher agent: search,
scrape, and (via fill_form) basic form interaction.

Requires `playwright install chromium` to have been run once — that
downloads real browser binaries and needs internet access, so it's a
one-time setup step on whichever laptop actually runs the Researcher role
in live mode, not something this code does automatically. `available` is
computed once at construction (by actually trying to launch and close a
browser) so callers can check cheaply afterward rather than re-probing on
every search call.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("llm_core.tools.web_browser")


class WebBrowser:
    def __init__(self, headless: bool = True, timeout_s: float = 20.0):
        self.headless = headless
        self.timeout_ms = timeout_s * 1000
        self._available = self._check_available()

    def _check_available(self) -> bool:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            return True
        except Exception as exc:
            logger.info("Playwright browser unavailable (%s) — web_browser will report unavailable; run `playwright install chromium` to enable it", exc)
            return False

    @property
    def available(self) -> bool:
        return self._available

    def search_and_summarize_links(self, query: str, max_results: int = 5) -> list[dict]:
        """Runs a real search and extracts (title, url, snippet) for the
        top results. Returns an empty list — never raises — on any
        failure (browser unavailable, navigation timeout, blocked/changed
        page layout), since a Researcher step should degrade to "no web
        results" rather than crash the whole graph over a flaky page load."""
        if not self._available:
            return []

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.goto(f"https://www.google.com/search?q={query}", timeout=self.timeout_ms)
                results = self._extract_results(page, max_results)
                browser.close()
            return results
        except Exception as exc:
            logger.info("web search failed for %r (%s); returning no results", query, exc)
            return []

    def _extract_results(self, page, max_results: int) -> list[dict]:
        results = []
        try:
            blocks = page.query_selector_all("div.g")[:max_results]
            for block in blocks:
                title_el = block.query_selector("h3")
                link_el = block.query_selector("a")
                snippet_el = block.query_selector("div[data-sncf], .VwiC3b")
                results.append({
                    "title": title_el.inner_text() if title_el else "",
                    "url": link_el.get_attribute("href") if link_el else "",
                    "snippet": snippet_el.inner_text() if snippet_el else "",
                })
        except Exception as exc:
            logger.info("result extraction failed (%s); page layout may have changed", exc)
        return results

    def fetch_page_text(self, url: str, max_chars: int = 2000) -> str:
        """Fetches a URL and returns its visible text content, truncated.
        Same fail-soft contract as search: returns "" rather than raising."""
        if not self._available:
            return ""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                page = browser.new_page()
                page.goto(url, timeout=self.timeout_ms)
                text = page.inner_text("body")
                browser.close()
            return text[:max_chars]
        except Exception as exc:
            logger.info("fetch_page_text failed for %r (%s)", url, exc)
            return ""
