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


def fetch_html(url: str, wait_selector: str | None = None, timeout_ms: int = 30000) -> str:
    """Load `url` in headless Chromium and return the rendered HTML.

    wait_selector: optional CSS selector to wait for before grabbing the
    HTML, for pages that populate content client-side after initial load.
    Retries a couple of times on failure — bot-detection blocks observed
    during build were sometimes transient.
    """
    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if resp is None or resp.status >= 400:
                    status = resp.status if resp else "no response"
                    raise RuntimeError(f"Fetch failed for {url}: HTTP {status}")
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=timeout_ms)
                else:
                    page.wait_for_timeout(1500)  # let client-side rendering settle
                return page.content()
            finally:
                browser.close()

    return _with_retries(_do)


def fetch_html_text(url: str, main_selector: str = "main", timeout_ms: int = 30000) -> str:
    """Like fetch_html, but returns the rendered visible text of
    `main_selector` instead of raw HTML — for sites where the data we need
    is plain text in the DOM rather than embedded JSON.
    """
    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                if resp is None or resp.status >= 400:
                    status = resp.status if resp else "no response"
                    raise RuntimeError(f"Fetch failed for {url}: HTTP {status}")
                page.wait_for_timeout(1500)
                return page.inner_text(main_selector)
            finally:
                browser.close()

    return _with_retries(_do)
