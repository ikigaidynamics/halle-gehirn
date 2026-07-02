"""Async httpx-Fetcher mit Rate-Limit, Retry+Backoff und Delta-Erkennung.

SEKUNDAER -- Primaerquelle sind lokale Dokumente in data/manual/.
Dieser Fetcher ergaenzt nur b-tu.de-Inhalte, wenn benoetigt.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx
import structlog

from halle_gehirn.config import get_settings

logger = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT: float = 30.0
_MAX_RETRIES: int = 3
_BACKOFF_BASE: float = 1.0
_BACKOFF_FACTOR: float = 2.0
_USER_AGENT: str = "HalleGehirn/0.1 (+https://b-tu.de; Forschungsprojekt)"
_DEFAULT_CONCURRENCY: int = 5


class FetchError(Exception):
    """HTTP-Abruf fehlgeschlagen nach allen Retries."""


@dataclass
class FetchResult:
    """Ergebnis eines HTTP-Abrufs.

    Attributes:
        url: Abgerufene URL.
        status_code: HTTP-Status.
        content: Response-Body als String.
        content_type: Content-Type-Header.
        fetched_at: Zeitstempel des Abrufs (UTC).
        content_hash: SHA-256 ueber den Body (Delta-Erkennung).
        etag: ETag-Header (falls vorhanden).
        last_modified: Last-Modified-Header (falls vorhanden).
        changed: True wenn Inhalt sich geaendert hat.
    """

    url: str
    status_code: int
    content: str
    content_type: str
    fetched_at: datetime
    content_hash: str = ""
    etag: str | None = None
    last_modified: str | None = None
    changed: bool = True

@dataclass
class _DeltaInfo:
    """Bekannte Delta-Informationen fuer eine URL."""

    content_hash: str | None = None
    etag: str | None = None
    last_modified: str | None = None


@dataclass
class _RateLimiter:
    """Token-Bucket Rate-Limiter fuer hoefliges Crawling."""

    min_interval: float = 1.0
    _last_request: float = field(default=0.0, init=False)

    async def wait(self) -> None:
        """Wartet bis der naechste Request erlaubt ist."""
        now = time.monotonic()
        elapsed = now - self._last_request
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()


def _compute_hash(content: str) -> str:
    """Berechnet SHA-256 ueber den Response-Body."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class Fetcher:
    """Async HTTP-Fetcher mit Rate-Limiting und Delta-Support.

    Liest erlaubte Domains und Rate-Limit aus der zentralen Config.
    Unterstuetzt ETag/Last-Modified fuer Conditional Requests und
    Content-Hash-Vergleich als Fallback-Delta-Erkennung.
    """

    def __init__(self) -> None:
        """Initialisiert den Fetcher mit Config-Werten."""
        settings = get_settings()
        self.allowed_domains: list[str] = [
            d.strip() for d in settings.crawler_domains.split(",")
        ]
        self.rate_limiter = _RateLimiter(
            min_interval=settings.crawler_rate_limit,
        )
        self.delta_cache: dict[str, _DeltaInfo] = {}
        logger.info(
            "fetcher_init",
            domains=self.allowed_domains,
            rate_limit_s=settings.crawler_rate_limit,
        )
    def _is_allowed(self, url: str) -> bool:
        """Prueft ob die URL zu einer erlaubten Domain gehoert."""
        hostname = urlparse(url).hostname or ""
        return any(hostname.endswith(d) for d in self.allowed_domains)

    def _build_headers(self, url: str) -> dict[str, str]:
        """Baut Request-Headers inkl. Conditional-Request-Header."""
        headers: dict[str, str] = {"User-Agent": _USER_AGENT}
        delta = self.delta_cache.get(url)
        if delta:
            if delta.etag:
                headers["If-None-Match"] = delta.etag
            if delta.last_modified:
                headers["If-Modified-Since"] = delta.last_modified
        return headers

    def _update_delta_cache(self, result: FetchResult) -> None:
        """Aktualisiert den Delta-Cache nach erfolgreichem Abruf."""
        self.delta_cache[result.url] = _DeltaInfo(
            content_hash=result.content_hash,
            etag=result.etag,
            last_modified=result.last_modified,
        )

    async def fetch(self, url: str) -> FetchResult:
        """Ruft eine URL ab mit Retry+Backoff und Delta-Erkennung.

        Sendet Conditional-Request-Header (If-None-Match, If-Modified-Since)
        falls fruehere Delta-Infos vorliegen. Respektiert das Rate-Limit.

        Args:
            url: Abzurufende URL.

        Returns:
            FetchResult mit Content und Delta-Info.

        Raises:
            FetchError: Alle Retries fehlgeschlagen.
            ValueError: URL gehoert nicht zu einer erlaubten Domain.
        """
        if not self._is_allowed(url):
            raise ValueError(f"Domain nicht erlaubt: {url}")

        await self.rate_limiter.wait()
        headers = self._build_headers(url)
        delta = self.delta_cache.get(url)
        return await self._do_fetch(url, headers=headers, delta=delta)
    async def _do_fetch(
        self,
        url: str,
        *,
        headers: dict[str, str],
        delta: _DeltaInfo | None,
    ) -> FetchResult:
        """Fuehrt den HTTP-Abruf mit Retries durch."""
        last_exc: Exception | None = None
        async with httpx.AsyncClient(
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
            headers=headers,
        ) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    return await self._attempt_fetch(client, url, delta=delta)
                except httpx.HTTPStatusError as exc:
                    last_exc = exc
                    if not self._is_retryable(exc.response.status_code):
                        break
                    await self._backoff(attempt, url, error=str(exc))
                except httpx.RequestError as exc:
                    last_exc = exc
                    await self._backoff(attempt, url, error=str(exc))
        raise FetchError(
            f"Abruf fehlgeschlagen nach {_MAX_RETRIES} Versuchen: {url}",
        ) from last_exc

    async def _attempt_fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        delta: _DeltaInfo | None,
    ) -> FetchResult:
        """Einzelner Fetch-Versuch mit Antwort-Auswertung."""
        response = await client.get(url)
        now = datetime.now(UTC)

        if response.status_code == 304:
            logger.debug("fetch_not_modified", url=url)
            return FetchResult(
                url=url, status_code=304, content="",
                content_type=response.headers.get("content-type", ""),
                fetched_at=now,
                content_hash=(delta.content_hash or "") if delta else "",
                etag=delta.etag if delta else None,
                last_modified=delta.last_modified if delta else None,
                changed=False,
            )
        response.raise_for_status()
        content = response.text
        content_hash = _compute_hash(content)
        etag = response.headers.get("etag")
        last_modified = response.headers.get("last-modified")
        content_type = response.headers.get("content-type", "")
        changed = not (delta and delta.content_hash == content_hash)

        result = FetchResult(
            url=url, status_code=response.status_code, content=content,
            content_type=content_type, fetched_at=now,
            content_hash=content_hash, etag=etag,
            last_modified=last_modified, changed=changed,
        )
        self._update_delta_cache(result)
        logger.info(
            "fetch_done", url=url, status=response.status_code,
            changed=changed, content_len=len(content),
        )
        return result

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        """True bei 429 oder 5xx-Fehlern."""
        return status_code in {429, 500, 502, 503, 504}

    @staticmethod
    async def _backoff(attempt: int, url: str, *, error: str) -> None:
        """Wartet exponentiell vor dem naechsten Retry."""
        wait = _BACKOFF_BASE * (_BACKOFF_FACTOR ** attempt)
        logger.warning(
            "fetch_retry", url=url, error=error,
            attempt=attempt + 1, wait_s=wait,
        )
        await asyncio.sleep(wait)

    async def fetch_batch(self, urls: list[str]) -> list[FetchResult]:
        """Ruft mehrere URLs mit Concurrency-Control ab.

        Verwendet ein Semaphore um die Parallelitaet zu begrenzen.
        Fehlgeschlagene URLs werden geloggt und uebersprungen.

        Args:
            urls: Liste der abzurufenden URLs.

        Returns:
            Liste der erfolgreichen FetchResults.
        """
        semaphore = asyncio.Semaphore(_DEFAULT_CONCURRENCY)
        logger.info("fetch_batch_start", url_count=len(urls))

        async def _limited_fetch(url: str) -> FetchResult | None:
            async with semaphore:
                try:
                    return await self.fetch(url)
                except (FetchError, ValueError) as exc:
                    logger.error(
                        "fetch_batch_url_failed",
                        url=url, error=str(exc),
                    )
                    return None

        tasks = [_limited_fetch(u) for u in urls]
        raw_results = await asyncio.gather(*tasks)
        results = [r for r in raw_results if r is not None]
        logger.info(
            "fetch_batch_done", total=len(urls),
            fetched=len(results),
            changed=sum(1 for r in results if r.changed),
        )
        return results
