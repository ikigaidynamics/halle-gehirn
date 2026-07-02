"""Tests fuer die Delta-Erkennung (Change Detection) im Fetcher.

Prueft _compute_hash, den delta_cache-Mechanismus und die Behandlung
von 304-Not-Modified-Antworten. Alle HTTP-Interaktionen werden gemockt.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from halle_gehirn.scraper.fetcher import Fetcher, _compute_hash

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_settings() -> SimpleNamespace:
    """Erzeugt ein Settings-aehnliches Objekt fuer Tests."""
    return SimpleNamespace(
        crawler_domains="example.com",
        crawler_rate_limit=0.0,
    )


def _mock_response(
    status_code: int = 200,
    text: str = "hello",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Erzeugt ein httpx.Response-aehnliches Mock-Objekt."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {"content-type": "text/html"}
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# _compute_hash
# ---------------------------------------------------------------------------


class TestComputeHash:
    """Tests fuer die _compute_hash Hilfsfunktion."""

    def test_compute_hash_deterministic(self) -> None:
        """Gleicher Input erzeugt immer denselben Hash."""
        content = "Hallo Welt, dies ist ein Test-Inhalt."
        hash_a = _compute_hash(content)
        hash_b = _compute_hash(content)
        assert hash_a == hash_b
        # SHA-256 erzeugt einen 64-Zeichen Hex-String
        assert len(hash_a) == 64

    def test_compute_hash_different_inputs(self) -> None:
        """Unterschiedliche Inputs erzeugen unterschiedliche Hashes."""
        hash_a = _compute_hash("Version 1 des Dokuments")
        hash_b = _compute_hash("Version 2 des Dokuments")
        assert hash_a != hash_b


# ---------------------------------------------------------------------------
# Delta-Mechanismus im Fetcher
# ---------------------------------------------------------------------------


class TestDeltaDetection:
    """Tests fuer die delta_cache-basierte Aenderungserkennung."""

    @pytest.mark.asyncio
    async def test_delta_unchanged_hash(self) -> None:
        """Zweiter Abruf mit identischem Inhalt -> changed=False.

        Ablauf:
        1. Erster fetch: kein Eintrag im delta_cache -> changed=True.
        2. Zweiter fetch: gleicher Inhalt, gleicher Hash -> changed=False.
        """
        same_content = "<html><body>Unveraenderter Inhalt</body></html>"
        resp_200 = _mock_response(status_code=200, text=same_content)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(return_value=resp_200)

        with (
            patch(
                "halle_gehirn.scraper.fetcher.get_settings",
                return_value=_fake_settings(),
            ),
            patch("halle_gehirn.scraper.fetcher.httpx.AsyncClient") as mock_ac,
        ):
            # AsyncClient als Context-Manager mocken
            mock_ac.return_value.__aenter__ = AsyncMock(
                return_value=mock_client,
            )
            mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)

            fetcher = Fetcher()
            url = "https://example.com/seite"

            # Erster Abruf -- kein delta_cache-Eintrag
            result_1 = await fetcher.fetch(url)
            assert result_1.changed is True
            assert url in fetcher.delta_cache
            assert fetcher.delta_cache[url].content_hash == _compute_hash(
                same_content,
            )

            # Zweiter Abruf -- gleicher Inhalt, Hash stimmt ueberein
            result_2 = await fetcher.fetch(url)
            assert result_2.changed is False
            assert result_2.status_code == 200

    @pytest.mark.asyncio
    async def test_delta_changed_content(self) -> None:
        """Zweiter Abruf mit anderem Inhalt -> changed=True.

        Ablauf:
        1. Erster fetch: Inhalt Version 1 -> changed=True.
        2. Zweiter fetch: Inhalt Version 2 -> changed=True (anderer Hash).
        """
        content_v1 = "<html><body>Version 1</body></html>"
        content_v2 = "<html><body>Version 2</body></html>"
        resp_v1 = _mock_response(status_code=200, text=content_v1)
        resp_v2 = _mock_response(status_code=200, text=content_v2)

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get = AsyncMock(side_effect=[resp_v1, resp_v2])

        with (
            patch(
                "halle_gehirn.scraper.fetcher.get_settings",
                return_value=_fake_settings(),
            ),
            patch("halle_gehirn.scraper.fetcher.httpx.AsyncClient") as mock_ac,
        ):
            mock_ac.return_value.__aenter__ = AsyncMock(
                return_value=mock_client,
            )
            mock_ac.return_value.__aexit__ = AsyncMock(return_value=False)

            fetcher = Fetcher()
            url = "https://example.com/seite"

            result_1 = await fetcher.fetch(url)
            assert result_1.changed is True

            result_2 = await fetcher.fetch(url)
            assert result_2.changed is True
            assert result_2.content_hash != result_1.content_hash

    @pytest.mark.asyncio
    async def test_delta_304_not_modified(self) -> None:
        """Server antwortet mit 304 -> changed=False.

        Ablauf:
        1. Erster fetch: normaler 200 mit ETag -> changed=True.
        2. Zweiter fetch: Fetcher sendet If-None-Match, Server gibt 304.
           -> changed=False, Content leer.
        """
        content = "<html><body>Seite mit ETag</body></html>"
        etag_value = '"abc123"'
        resp_200 = _mock_response(
            status_code=200,
            text=content,
            headers={
                "content-type": "text/html",
                "etag": etag_value,
                "last-modified": "Wed, 01 Jul 2026 12:00:00 GMT",
            },
        )
        resp_304 = _mock_response(
            status_code=304,
            text="",
            headers={"content-type": "text/html"},
        )

        mock_client_first = AsyncMock(spec=httpx.AsyncClient)
        mock_client_first.get = AsyncMock(return_value=resp_200)

        mock_client_second = AsyncMock(spec=httpx.AsyncClient)
        mock_client_second.get = AsyncMock(return_value=resp_304)

        with (
            patch(
                "halle_gehirn.scraper.fetcher.get_settings",
                return_value=_fake_settings(),
            ),
            patch("halle_gehirn.scraper.fetcher.httpx.AsyncClient") as mock_ac,
        ):
            # Verschiedene Client-Instanzen fuer die zwei Aufrufe
            ctx_first = MagicMock()
            ctx_first.__aenter__ = AsyncMock(
                return_value=mock_client_first,
            )
            ctx_first.__aexit__ = AsyncMock(return_value=False)

            ctx_second = MagicMock()
            ctx_second.__aenter__ = AsyncMock(
                return_value=mock_client_second,
            )
            ctx_second.__aexit__ = AsyncMock(return_value=False)

            mock_ac.side_effect = [ctx_first, ctx_second]

            fetcher = Fetcher()
            url = "https://example.com/seite"

            # Erster Abruf -- 200 mit ETag
            result_1 = await fetcher.fetch(url)
            assert result_1.changed is True
            assert result_1.etag == etag_value
            assert url in fetcher.delta_cache
            assert fetcher.delta_cache[url].etag == etag_value

            # Zweiter Abruf -- 304 Not Modified
            result_2 = await fetcher.fetch(url)
            assert result_2.changed is False
            assert result_2.status_code == 304
            assert result_2.content == ""
            # Delta-Info bleibt erhalten
            assert result_2.etag == etag_value
