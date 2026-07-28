"""Tests fuer /admin/wissen Endpoints.

Testet Auth, Bestand-Uebersicht, Vokabular-CRUD, Dokument-Upload/-Delete,
Ingest-Job-Lifecycle. Alle externen Dienste werden gemockt.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from halle_gehirn.api.main import create_app
from halle_gehirn.config import Settings, get_settings
from halle_gehirn.pipeline.ingest import ManifestEntry


def _test_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "qdrant_url": "http://localhost:6335",
        "qdrant_collection": "halle_wissen_test",
        "ollama_url": "http://localhost:11434",
        "admin_api_key": "test-secret-key",
        "cors_origins": "*",
        "rate_limit_rpm": 1000,
        "use_query_transform": False,
        "use_grounding_check": False,
        "otel_enabled": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@contextmanager
def _patched_app() -> Any:
    """Erzeugt App mit gepatchter Pipeline + Settings."""
    get_settings.cache_clear()
    settings = _test_settings()
    with (
        patch("halle_gehirn.config.get_settings", return_value=settings),
        patch(
            "halle_gehirn.api.main.get_settings", return_value=settings,
        ),
        patch(
            "halle_gehirn.api.routes.admin.get_settings",
            return_value=settings,
        ),
        patch(
            "halle_gehirn.api.routes.health.get_settings",
            return_value=settings,
        ),
        patch("halle_gehirn.api.main.build_query_pipeline") as mock_build,
    ):
        mock_pipeline = MagicMock()
        mock_pipeline.settings = settings
        mock_build.return_value = mock_pipeline
        app = create_app()
        with TestClient(app) as client:
            yield client


_HEADERS = {"X-API-Key": "test-secret-key"}

_SAMPLE_ENTRIES = [
    ManifestEntry(
        datei="abschlussarbeiten/test.pdf",
        titel="Testtitel",
        doc_type="abschlussarbeit",
        bereich=["transfer"],
        herkunft="lehrstuhl_at",
        quelltyp="primaer",
        vertraulichkeit="intern",
        status="final",
        thema=["mensch_roboter_kollaboration"],
        autor=["wang_zhili"],
    ),
]

_SAMPLE_INDEXED = [
    {
        "datei": "abschlussarbeiten/test.pdf",
        "titel": "Testtitel",
        "chunk_count": 26,
        "source_hash": "abc123",
        "doc_type": "abschlussarbeit",
    },
]


class TestAdminWissenAuth:
    """Auth-Tests fuer /admin/wissen Endpoints."""

    def test_bestand_without_key_returns_401(self) -> None:
        with _patched_app() as client:
            resp = client.get("/admin/wissen/bestand")
            assert resp.status_code == 401

    def test_vokabular_without_key_returns_401(self) -> None:
        with _patched_app() as client:
            resp = client.get("/admin/wissen/vokabular")
            assert resp.status_code == 401


class TestBestand:
    """Tests fuer GET /admin/wissen/bestand."""

    @patch(
        "halle_gehirn.api.routes.admin_wissen.list_indexed_documents",
        return_value=_SAMPLE_INDEXED,
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen.load_manifest_entries",
        return_value=_SAMPLE_ENTRIES,
    )
    def test_bestand_returns_entries(
        self, _m1: MagicMock, _m2: MagicMock,
    ) -> None:
        with _patched_app() as client:
            resp = client.get("/admin/wissen/bestand", headers=_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["manifest_entries"]) == 1
            entry = data["manifest_entries"][0]
            assert entry["datei"] == "abschlussarbeiten/test.pdf"
            assert entry["doc_type"] == "abschlussarbeit"
            assert entry["doc_type_label"] == "Abschlussarbeit"
            assert entry["is_indexed"] is True
            assert data["total_chunks"] == 26

    @patch(
        "halle_gehirn.api.routes.admin_wissen.list_indexed_documents",
        return_value=[{
            "datei": "orphan.pdf", "titel": "Orphan", "chunk_count": 5,
            "source_hash": "xyz", "doc_type": "sonstiges",
        }],
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen.load_manifest_entries",
        return_value=[],
    )
    def test_bestand_orphan_detection(
        self, _m1: MagicMock, _m2: MagicMock,
    ) -> None:
        with _patched_app() as client:
            resp = client.get("/admin/wissen/bestand", headers=_HEADERS)
            data = resp.json()
            assert data["indexed_docs"][0]["in_manifest"] is False


class TestVokabular:
    """Tests fuer GET/POST /admin/wissen/vokabular."""

    @patch(
        "halle_gehirn.api.routes.admin_wissen.list_upload_sorten",
        return_value=["abschlussarbeiten", "anlagen"],
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen.load_vokabular_choices",
        return_value={"thema": {"mrk": "MRK"}, "anlage": {}},
    )
    def test_vokabular_returns_choices(
        self, _m1: MagicMock, _m2: MagicMock,
    ) -> None:
        with _patched_app() as client:
            resp = client.get("/admin/wissen/vokabular", headers=_HEADERS)
            assert resp.status_code == 200
            data = resp.json()
            assert "thema" in data["choices"]
            assert "abschlussarbeiten" in data["sorten"]

    @patch("halle_gehirn.api.routes.admin_wissen.save_vokabular_entry")
    def test_create_vokabular_ok(self, mock_save: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/vokabular",
                headers=_HEADERS,
                json={"facet": "anlage", "slug": "neuer_roboter", "label": "Neuer Roboter"},
            )
            assert resp.status_code == 200
            assert resp.json()["slug"] == "neuer_roboter"
            mock_save.assert_called_once()

    def test_create_vokabular_invalid_facet(self) -> None:
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/vokabular",
                headers=_HEADERS,
                json={"facet": "bereich", "slug": "test", "label": "Test"},
            )
            assert resp.status_code == 422

    @patch(
        "halle_gehirn.api.routes.admin_wissen.save_vokabular_entry",
        side_effect=ValueError("Slug 'test' existiert bereits in 'anlage'."),
    )
    def test_create_vokabular_duplicate(self, _mock: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/vokabular",
                headers=_HEADERS,
                json={"facet": "anlage", "slug": "test", "label": "Test"},
            )
            assert resp.status_code == 409


class TestDokumente:
    """Tests fuer POST/DELETE /admin/wissen/dokumente."""

    @patch("halle_gehirn.api.routes.admin_wissen.save_manifest_entry")
    @patch(
        "halle_gehirn.api.routes.admin_wissen.save_uploaded_file",
        return_value="data/manual/anlagen/test.pdf",
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen.validate_entry",
        return_value=[],
    )
    def test_create_dokument_ok(
        self, _v: MagicMock, _s: MagicMock, _m: MagicMock,
    ) -> None:
        meta = json.dumps({
            "sorte": "anlagen",
            "titel": "Testdokument",
            "doc_type": "anlagendoku",
            "bereich": ["infrastruktur"],
            "herkunft": "lehrstuhl_at",
        })
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/dokumente",
                headers=_HEADERS,
                files={"file": ("test.pdf", b"fake-pdf-data", "application/pdf")},
                data={"metadata": meta},
            )
            assert resp.status_code == 200
            assert resp.json()["datei"] == "anlagen/test.pdf"

    def test_create_dokument_missing_sorte(self) -> None:
        meta = json.dumps({"titel": "Test", "doc_type": "sonstiges"})
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/dokumente",
                headers=_HEADERS,
                files={"file": ("test.pdf", b"data", "application/pdf")},
                data={"metadata": meta},
            )
            assert resp.status_code == 422
            assert "sorte" in resp.json()["detail"]

    @patch(
        "halle_gehirn.api.routes.admin_wissen.validate_entry",
        return_value=["'bereich' ist ein Pflichtfeld."],
    )
    def test_create_dokument_validation_error(
        self, _mock: MagicMock,
    ) -> None:
        meta = json.dumps({
            "sorte": "anlagen", "titel": "Test", "doc_type": "sonstiges",
        })
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/dokumente",
                headers=_HEADERS,
                files={"file": ("test.pdf", b"data", "application/pdf")},
                data={"metadata": meta},
            )
            assert resp.status_code == 422

    @patch(
        "halle_gehirn.api.routes.admin_wissen.delete_manifest_entry",
        return_value=True,
    )
    @patch("halle_gehirn.api.routes.admin_wissen.delete_by_source_hash")
    @patch(
        "halle_gehirn.api.routes.admin_wissen.list_indexed_documents",
        return_value=[{"datei": "a.pdf", "source_hash": "abc", "chunk_count": 10}],
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen.compute_source_hash",
        return_value="abc",
    )
    @patch(
        "halle_gehirn.api.routes.admin_wissen._MANUAL_DIR",
    )
    def test_delete_dokument(
        self, mock_dir: MagicMock, _h: MagicMock,
        _l: MagicMock, _d: MagicMock, _m: MagicMock,
    ) -> None:
        # Mock Path / datei to make file_path.exists() return True
        mock_path = MagicMock()
        mock_path.exists.return_value = True
        mock_dir.__truediv__ = MagicMock(return_value=mock_path)

        with _patched_app() as client:
            resp = client.delete(
                "/admin/wissen/dokumente/anlagen/test.pdf",
                headers=_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["deleted_from_manifest"] is True
            assert data["deleted_from_qdrant"] is True


class TestDokumentChunks:
    """Tests fuer GET /admin/wissen/dokumente/{datei}/chunks."""

    _MOCK_CHUNKS: ClassVar[list[dict[str, Any]]] = [
        {
            "point_id": "aaa",
            "payload": {
                "datei": "abschlussarbeiten/test.pdf",
                "titel": "Testtitel",
                "chunk_index": 0,
                "text": "Erster Chunk Text hier.",
                "breadcrumb": "1 Einleitung",
                "context_prefix": "LLM-generierter Kontext.",
                "page": 5,
                "table_ref": None,
            },
        },
        {
            "point_id": "bbb",
            "payload": {
                "datei": "abschlussarbeiten/test.pdf",
                "titel": "Testtitel",
                "chunk_index": 1,
                "text": "| A | B |\n|---|---|\n| 1 | 2 |",
                "breadcrumb": "2 Methodik",
                "context_prefix": None,
                "page": 8,
                "table_ref": "table_001",
            },
        },
    ]

    @patch(
        "halle_gehirn.api.routes.admin_wissen.get_chunks_by_datei",
        return_value=_MOCK_CHUNKS,
    )
    def test_chunks_returns_details(self, _mock: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.get(
                "/admin/wissen/dokumente/abschlussarbeiten/test.pdf/chunks",
                headers=_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["datei"] == "abschlussarbeiten/test.pdf"
            assert data["chunk_count"] == 2
            assert data["chunks"][0]["chunk_index"] == 0
            assert data["chunks"][0]["breadcrumb"] == "1 Einleitung"
            assert data["chunks"][0]["context_prefix"] == "LLM-generierter Kontext."
            assert data["chunks"][0]["is_table"] is False
            assert data["chunks"][0]["token_count"] > 0
            assert data["chunks"][1]["is_table"] is True

    @patch(
        "halle_gehirn.api.routes.admin_wissen.get_chunks_by_datei",
        return_value=[],
    )
    def test_chunks_not_found(self, _mock: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.get(
                "/admin/wissen/dokumente/nonexistent/file.pdf/chunks",
                headers=_HEADERS,
            )
            assert resp.status_code == 404

    def test_chunks_without_key_returns_401(self) -> None:
        with _patched_app() as client:
            resp = client.get(
                "/admin/wissen/dokumente/test.pdf/chunks",
            )
            assert resp.status_code == 401


class TestIngest:
    """Tests fuer POST /admin/wissen/ingest + GET Status."""

    @patch("halle_gehirn.api.routes.admin_wissen.start_job")
    @patch(
        "halle_gehirn.api.routes.admin_wissen.create_job",
        return_value="test123",
    )
    def test_start_ingest(
        self, _c: MagicMock, _s: MagicMock,
    ) -> None:
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/ingest",
                headers=_HEADERS,
                json={"selected_dateien": ["anlagen/test.pdf"]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "accepted"
            assert data["job_id"] == "test123"

    def test_start_ingest_empty_dateien(self) -> None:
        with _patched_app() as client:
            resp = client.post(
                "/admin/wissen/ingest",
                headers=_HEADERS,
                json={"selected_dateien": []},
            )
            assert resp.status_code == 422

    @patch(
        "halle_gehirn.api.routes.admin_wissen.get_job",
        return_value=None,
    )
    def test_ingest_status_not_found(self, _mock: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.get(
                "/admin/wissen/ingest/nonexistent",
                headers=_HEADERS,
            )
            assert resp.status_code == 404


@dataclass
class _MockJob:
    """Minimal Job-Mock fuer Status-Tests."""

    job_id: str = "test123"
    status: str = "completed"
    events: list[dict[str, Any]] = field(default_factory=lambda: [
        {"phase": "done", "status": "completed", "detail": "10 Chunks.",
         "datei": "", "doc_index": 2, "doc_total": 2},
    ])
    stats: dict[str, Any] | None = field(default_factory=lambda: {
        "docs_total": 2, "chunks_total": 10,
    })
    error: str | None = None


class TestIngestStatus:
    """Tests fuer GET /admin/wissen/ingest/{job_id}."""

    @patch(
        "halle_gehirn.api.routes.admin_wissen.get_job",
        return_value=_MockJob(),
    )
    def test_ingest_status_completed(self, _mock: MagicMock) -> None:
        with _patched_app() as client:
            resp = client.get(
                "/admin/wissen/ingest/test123",
                headers=_HEADERS,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "completed"
            assert data["progress"] == 1.0
            assert data["stats"]["chunks_total"] == 10
