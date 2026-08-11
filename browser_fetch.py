"""
Shared headless-browser fetch helper.

Plain `requests` gets a 403 from at least rentals.ca (confirmed during
build) — likely TLS-fingerprint / non-browser-header bot detection, common
on rental aggregators. A real (headless) Chromium session passes those
checks. Every scraper that needs a live page should go through here rather
than rolling its own requests/Playwright calls, so there's one place to
tune timeouts, retries, and the user agent.

This does NOT defeat Cloudflare's interactive challenges — it's a plain
page load, not a challenge-solver. Sites behind an active JS challenge
(see scrapers/rentcafe.py) may still fail intermittently; that's handled
as a soft failure in main.py, not papered over here.

For scrapers that make MANY requests to the same site in one run (e.g.
rentals_ca.py drilling into ~20+ building pages), use BrowserSession
instead of the standalone functions below: it launches Chromium ONCE and
reuses it across requests (a fresh browser launch per request was both
slow and, we suspect, part of what was tripping rentals.ca's rate
limiter — repeated 429s were observed hitting it request-by-request even
though each request looks like an independent browser session).
BrowserSession also paces requests with a small delay, which plain
fetch_html/fetch_html_text don't need since they're one-shot.
"""
from __future__ import annotations
import time
from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

RETRIES = 2
RETRY_DELAY_SEC = 5


def _with_retries(fn):
    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                time.sleep(RETRY_DELAY_SEC)
    raise last_err


class BrowserSession:
    """One Chromium process reused across many fetches, with pacing.

    Usage:
        with BrowserSession() as s:
            html = s.fetch_html(url1)
            html2 = s.fetch_html(url2)   # reuses the same browser
    """

    def __init__(self, request_delay_sec: float = 1.5):
        self.request_delay_sec = request_delay_sec
        self._playwright = None
        self._browser = None
        self._request_count = 0

    def __enter__(self) -> "BrowserSession":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch()
        return self

    def __exit__(self, *exc_info):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _pace(self):
        if self._request_count > 0:
            time.sleep(self.request_delay_sec)
        self._request_count += 1

    def fetch_html(self, url: str, wait_selector: str | None = None, timeout_ms: int = 30000) -> str:
        def _do():
            self._pace()
            page = self._browser.new_page(user_agent=USER_AGENT)
            try:
                resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if resp is None or resp.status >= 400:
                    status = resp.status if resp else "no response"
                    raise RuntimeError(f"Fetch failed for {url}: HTTP {status}")
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=timeout_ms)
                else:
                    page.wait_for_timeout(1500)
                return page.content()
            finally:
                page.close()

        return _with_retries(_do)

    def fetch_html_text(self, url: str, main_selector: str = "main", timeout_ms: int = 30000) -> str:
        def _do():
            self._pace()
            page = self._browser.new_page(user_agent=USER_AGENT)
            try:
                resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if resp is None or resp.status >= 400:
                    status = resp.status if resp else "no response"
                    raise RuntimeError(f"Fetch failed for {url}: HTTP {status}")
                page.wait_for_timeout(1500)
                return page.inner_text(main_selector)
            finally:
                page.close()

        return _with_retries(_do)


def fetch_html(url: str, wait_selector: str | None = None, timeout_ms: int = 30000) -> str:
    """One-shot fetch (launches and tears down its own Chromium). Fine for
    scrapers that only make a request or two per run — use BrowserSession
    instead for anything that loops over many URLs.
    """
    with BrowserSession() as s:
        return s.fetch_html(url, wait_selector=wait_selector, timeout_ms=timeout_ms)


def fetch_html_text(url: str, main_selector: str = "main", timeout_ms: int = 30000) -> str:
    """One-shot version of BrowserSession.fetch_html_text — see fetch_html."""
    with BrowserSession() as s:
        return s.fetch_html_text(url, main_selector=main_selector, timeout_ms=timeout_ms)
