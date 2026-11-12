"""Tests fuer das automatische Browser-Oeffnen im Standalone-Bundle."""
from __future__ import annotations

import webbrowser

from halle_gehirn.bundle import entrypoint


def test_open_browser_when_up_oeffnet_url(monkeypatch) -> None:
    """Ohne Health-Gate: URL wird nach kurzer Verzoegerung geoeffnet."""
    aufgerufen: list[str] = []
    monkeypatch.setattr(webbrowser, "open", lambda url: aufgerufen.append(url))

    entrypoint.open_browser_when_up("http://localhost:8001/", delay_s=0.0)

    assert aufgerufen == ["http://localhost:8001/"]


def test_open_browser_when_up_verschlingt_browser_fehler(monkeypatch) -> None:
    """Browser-Start ist best-effort: Fehler loesen keinen Crash aus."""

    def _platte(_url: str) -> None:
        raise RuntimeError("kein Browser verfuegbar")

    monkeypatch.setattr(webbrowser, "open", _platte)

    entrypoint.open_browser_when_up("http://localhost:8001/", delay_s=0.0)


def test_settings_open_browser_default_aus() -> None:
    """Dev-Default: kein automatisches Browser-Oeffnen."""
    from halle_gehirn.config import Settings

    assert Settings(_env_file=None).open_browser is False
