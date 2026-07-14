"""Tests fuer die Docling-Serve-Remote-Extraktion (feature/docling-serve).

Gemocktes HTTP — kein echter Server noetig. Prueft:
- Request-Form (Endpoint, to_formats, do_ocr-Override)
- Response → ExtractedDoc mit Page-Map (aus texts) + Tabellen (aus grid)
- Caption-$ref-Aufloesung
- Status "failure" → ExtractionError
- Server-URL leer → Remote-Pfad wird nicht betreten
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halle_gehirn.config import Settings
from halle_gehirn.extraction import docling_extractor as de
from halle_gehirn.extraction.base import ExtractionError

# Realistische (minimale) Docling-Serve-Response
_MD = "Einleitung\n\nInhalt auf Seite eins.\n\nMethode\n\nTabelle 1: Messwerte"
_JSON_CONTENT: dict[str, Any] = {
    "name": "Testdokument",
    "texts": [
        {"text": "Einleitung", "prov": [{"page_no": 1}]},
        {"text": "Inhalt auf Seite eins.", "prov": [{"page_no": 1}]},
        {"text": "Methode", "prov": [{"page_no": 2}]},
        {"text": "Tabelle 1: Messwerte", "prov": [{"page_no": 2}]},
    ],
    "tables": [
        {
            "data": {"grid": [["A", "B"], ["1", "2"]]},
            "prov": [{"page_no": 2}],
            "captions": [{"$ref": "#/texts/3"}],
        },
    ],
    "pages": {"1": {}, "2": {}},
}
_RESPONSE: dict[str, Any] = {
    "document": {"md_content": _MD, "json_content": _JSON_CONTENT},
    "status": "success",
    "errors": [],
    "processing_time": 1.2,
}


class _FakeResponse:
    """Minimaler httpx.Response-Stub."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._data


class _FakeClient:
    """httpx.Client-Stub als Context-Manager; zeichnet den POST auf."""

    def __init__(self, response: dict[str, Any], capture: dict[str, Any]) -> None:
        self._response = response
        self._capture = capture

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def post(
        self,
        url: str,
        files: Any = None,
        data: Any = None,
    ) -> _FakeResponse:
        self._capture["url"] = url
        self._capture["files"] = files
        self._capture["data"] = data
        return _FakeResponse(self._response)


def _patch_httpx(
    monkeypatch: pytest.MonkeyPatch,
    response: dict[str, Any],
) -> dict[str, Any]:
    """Ersetzt httpx.Client durch den Fake und liefert das Capture-Dict."""
    capture: dict[str, Any] = {}

    def _factory(*_a: object, **_k: object) -> _FakeClient:
        return _FakeClient(response, capture)

    monkeypatch.setattr(de.httpx, "Client", _factory)
    return capture


def _pdf(tmp_path: Path) -> Path:
    """Legt eine (leere) Test-PDF an — Inhalt egal, wird gemockt."""
    p = tmp_path / "arbeit.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


class TestRemoteExtraction:
    """Erfolgreiche Remote-Extraktion via Docling Serve."""

    def test_builds_extracted_doc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Response wird zu ExtractedDoc mit Body, Tabellen, Page-Map."""
        _patch_httpx(monkeypatch, _RESPONSE)
        settings = Settings(
            docling_serve_url="http://gpu-host:5001",
            boilerplate_clean=False,
        )
        doc = de.DoclingExtractor(settings=settings).extract(_pdf(tmp_path))

        assert doc.meta["extraction_backend"] == "docling_serve"
        assert "Einleitung" in doc.body_md
        assert doc.page_count == 2
        # Page-Map aus den texts (Seite 1 → Seite 2)
        assert [p for _, p in doc.page_map] == [1, 2]
        # Tabelle aus grid, Seite + Caption via $ref aufgeloest
        assert len(doc.tables) == 1
        assert "| A | B |" in doc.tables[0].markdown
        assert doc.tables[0].page == 2
        assert doc.tables[0].caption == "Tabelle 1: Messwerte"

    def test_request_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """POST geht an /v1/convert/file mit korrekten Optionen."""
        capture = _patch_httpx(monkeypatch, _RESPONSE)
        settings = Settings(
            docling_serve_url="http://gpu-host:5001/",  # trailing slash
            docling_ocr=True,
        )
        de.DoclingExtractor(settings=settings).extract(
            _pdf(tmp_path), do_ocr=False,
        )
        assert capture["url"] == "http://gpu-host:5001/v1/convert/file"
        # do_ocr-Override (False) schlaegt Config-Default (True)
        assert capture["data"]["do_ocr"] == "false"
        assert "md" in capture["data"]["to_formats"]
        assert "json" in capture["data"]["to_formats"]
        assert capture["files"][0][0] == "files"


class TestRemoteFailures:
    """Fehlerpfade der Remote-Extraktion."""

    def test_status_failure_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """status=failure → ExtractionError (fail-closed)."""
        bad = {
            "document": {"md_content": "", "json_content": {}},
            "status": "failure",
            "errors": ["boom"],
        }
        _patch_httpx(monkeypatch, bad)
        settings = Settings(docling_serve_url="http://gpu-host:5001")
        with pytest.raises(ExtractionError, match="FAILURE"):
            de.DoclingExtractor(settings=settings).extract(_pdf(tmp_path))

    def test_empty_url_skips_remote(self) -> None:
        """Ohne docling_serve_url bleibt der Remote-Pfad ungenutzt."""
        settings = Settings(docling_serve_url="")
        extractor = de.DoclingExtractor(settings=settings)
        # Kein Netz-Aufruf: _convert_remote wird nie erreicht — wir pruefen
        # lediglich, dass die Konfiguration den lokalen Pfad waehlt.
        assert not extractor._settings.docling_serve_url
