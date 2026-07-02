"""Optionaler Playwright-Fetcher fuer JavaScript-gerenderte Seiten.

Lazy Import: Playwright wird erst bei Aufruf importiert, damit die
Abhaengigkeit optional bleibt. Fuer den sekundaeren Crawler nur noetig,
wenn b-tu.de-Seiten JavaScript-Rendering erfordern.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import structlog

from halle_gehirn.scraper.fetcher import FetchResult

logger = structlog.get_logger(__name__)

_DEFAULT_WAIT_MS: int = 3000
_USER_AGENT: str = "HalleGehirn/0.1 (+https://b-tu.de; Forschungsprojekt)"


class PlaywrightNotAvailableError(Exception):
    """Playwright ist nicht installiert oder nicht initialisiert."""


def _compute_hash(content: str) -> str:
    """Berechnet SHA-256 ueber den gerenderten HTML-Inhalt."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _check_playwright_available() -> None:
    """Prueft ob Playwright importierbar ist.

    Raises:
        PlaywrightNotAvailableError: Playwright nicht installiert.
    """
    try:
        import playwright.async_api  # noqa: F401
    except ImportError as exc:
        logger.warning(
            "playwright_not_available",
            hint="pip install playwright && playwright install chromium",
        )
        raise PlaywrightNotAvailableError(
            "Playwright nicht installiert. Installiere mit: "
            "pip install playwright && playwright install chromium"
        ) from exc

class JsFetcher:
    """Playwright-basierter Fetcher fuer JS-gerenderte Seiten.

    Verwendet Playwright (Chromium, headless) um Seiten vollstaendig
    zu rendern, bevor das HTML extrahiert wird. Graceful degradation:
    wenn Playwright nicht installiert ist, wird ein Fehler geloggt und
    eine PlaywrightNotAvailableError ausgeloest.
    """

    def __init__(self, *, wait_ms: int = _DEFAULT_WAIT_MS) -> None:
        """Initialisiert den JsFetcher.

        Args:
            wait_ms: Wartezeit nach Seitenlade fuer JS-Rendering (ms).

        Raises:
            PlaywrightNotAvailableError: Playwright nicht verfuegbar.
        """
        _check_playwright_available()
        self.wait_ms = wait_ms
        logger.info("js_fetcher_init", wait_ms=wait_ms)

    async def fetch(self, url: str) -> FetchResult:
        """Rendert eine Seite via Playwright und gibt das HTML zurueck.

        Startet einen headless Chromium-Browser, navigiert zur URL,
        wartet auf JS-Rendering und extrahiert das gerenderte HTML.

        Args:
            url: Abzurufende URL.

        Returns:
            FetchResult mit gerendertem HTML als content.

        Raises:
            PlaywrightNotAvailableError: Playwright nicht installiert.
        """
        from playwright.async_api import async_playwright

        logger.info("js_fetch_start", url=url, wait_ms=self.wait_ms)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, wait_until="networkidle")
                await page.wait_for_timeout(self.wait_ms)
                html = await page.content()
            finally:
                await browser.close()

        content_hash = _compute_hash(html)
        now = datetime.now(UTC)

        logger.info(
            "js_fetch_done", url=url, html_len=len(html),
        )

        return FetchResult(
            url=url,
            status_code=200,
            content=html,
            content_type="text/html",
            fetched_at=now,
            content_hash=content_hash,
            changed=True,
        )

    async def fetch_batch(self, urls: list[str]) -> list[FetchResult]:
        """Rendert mehrere Seiten sequentiell via Playwright.

        Playwright-Browser-Instanzen sind ressourcenintensiv, daher
        wird sequentiell statt parallel gearbeitet.

        Args:
            urls: Liste der abzurufenden URLs.

        Returns:
            Liste der erfolgreichen FetchResults.
        """
        results: list[FetchResult] = []
        logger.info("js_fetch_batch_start", url_count=len(urls))

        for url in urls:
            try:
                result = await self.fetch(url)
                results.append(result)
            except Exception as exc:
                logger.error(
                    "js_fetch_batch_url_failed",
                    url=url, error=str(exc),
                )

        logger.info(
            "js_fetch_batch_done",
            total=len(urls), fetched=len(results),
        )
        return results
