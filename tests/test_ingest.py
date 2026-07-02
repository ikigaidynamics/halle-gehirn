"""Tests fuer die Ingest-Pipeline (Manifest, Vokabular, IDs, Payloads)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from halle_gehirn.pipeline.chunker import Chunk
from halle_gehirn.pipeline.ingest import (
    IngestError,
    VokabularValidationError,
    build_chunk_payload,
    compute_source_hash,
    deterministic_chunk_id,
    load_manifest,
    load_vokabular,
    validate_enums,
    validate_manifest_against_vokabular,
)


class TestLoadManifest:
    """Tests fuer Manifest-Parsing."""

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        """Gueltiges Manifest wird korrekt geladen."""
        manifest = {
            "dokumente": [
                {
                    "datei": "test.pdf",
                    "titel": "Testdokument",
                    "doc_type": "handbuch",
                    "bereich": ["forschung"],
                    "herkunft": "lehrstuhl_at",
                    "quelltyp": "primaer",
                },
            ],
        }
        p = tmp_path / "manifest.yaml"
        p.write_text(yaml.dump(manifest), encoding="utf-8")
        entries = load_manifest(p)
        assert len(entries) == 1
        assert entries[0].datei == "test.pdf"
        assert entries[0].titel == "Testdokument"
        assert entries[0].bereich == ["forschung"]

    def test_load_manifest_missing_raises(self, tmp_path: Path) -> None:
        """Fehlende Manifest-Datei loest IngestError aus."""
        with pytest.raises(IngestError, match="nicht gefunden"):
            load_manifest(tmp_path / "nonexistent.yaml")

    def test_load_manifest_empty_raises(self, tmp_path: Path) -> None:
        """Leeres Manifest loest IngestError aus."""
        p = tmp_path / "manifest.yaml"
        p.write_text("", encoding="utf-8")
        with pytest.raises(IngestError, match="leer"):
            load_manifest(p)

    def test_scalar_bereich_converted_to_list(self, tmp_path: Path) -> None:
        """Einzelner bereich-String wird zur Liste konvertiert."""
        manifest = {
            "dokumente": [
                {
                    "datei": "x.pdf",
                    "titel": "X",
                    "doc_type": "flyer",
                    "bereich": "transfer",
                    "herkunft": "mdz",
                },
            ],
        }
        p = tmp_path / "manifest.yaml"
        p.write_text(yaml.dump(manifest), encoding="utf-8")
        entries = load_manifest(p)
        assert entries[0].bereich == ["transfer"]


class TestLoadVokabular:
    """Tests fuer Vokabular-Parsing."""

    def test_load_valid_vokabular(self, tmp_path: Path) -> None:
        """Gueltiges Vokabular wird als Registry geladen."""
        vokabular = {
            "thema": {"mrk": "MRK"},
            "anlage": {"roboter_1": "Roboter 1"},
            "projekt": {"direct": "DIRECT"},
            "ansprechperson": {"mueller": "Mueller"},
        }
        p = tmp_path / "vokabular.yaml"
        p.write_text(yaml.dump(vokabular), encoding="utf-8")
        registry = load_vokabular(p)
        assert "mrk" in registry["thema"]
        assert "roboter_1" in registry["anlage"]

    def test_load_vokabular_missing_raises(self, tmp_path: Path) -> None:
        """Fehlende Vokabular-Datei loest IngestError aus."""
        with pytest.raises(IngestError, match="nicht gefunden"):
            load_vokabular(tmp_path / "nonexistent.yaml")


class TestVokabularValidation:
    """Tests fuer Slug-Validierung gegen Vokabular."""

    def test_valid_slugs_pass(self) -> None:
        """Bekannte Slugs passieren die Validierung."""
        from halle_gehirn.pipeline.ingest import ManifestEntry

        entry = ManifestEntry(
            datei="test.pdf",
            titel="Test",
            doc_type="handbuch",
            bereich=["forschung"],
            herkunft="lehrstuhl_at",
            thema=["mrk"],
            anlage=["roboter"],
        )
        registry = {
            "thema": {"mrk"},
            "anlage": {"roboter"},
            "projekt": set(),
            "ansprechperson": set(),
        }
        # Sollte NICHT raisen
        validate_manifest_against_vokabular([entry], registry)

    def test_unknown_slug_raises(self) -> None:
        """Unbekannter Slug loest VokabularValidationError aus."""
        from halle_gehirn.pipeline.ingest import ManifestEntry

        entry = ManifestEntry(
            datei="test.pdf",
            titel="Test",
            doc_type="handbuch",
            bereich=["forschung"],
            herkunft="lehrstuhl_at",
            anlage=["GIBT_ES_NICHT"],
        )
        registry = {
            "thema": set(),
            "anlage": {"roboter"},
            "projekt": set(),
            "ansprechperson": set(),
        }
        with pytest.raises(VokabularValidationError, match="GIBT_ES_NICHT"):
            validate_manifest_against_vokabular([entry], registry)


class TestEnumValidation:
    """Tests fuer Enum-Validierung."""

    def test_valid_enums_pass(self) -> None:
        """Gueltige Enum-Werte passieren die Validierung."""
        from halle_gehirn.pipeline.ingest import ManifestEntry

        entry = ManifestEntry(
            datei="test.pdf",
            titel="Test",
            doc_type="handbuch",
            bereich=["forschung"],
            herkunft="lehrstuhl_at",
            quelltyp="primaer",
        )
        validate_enums([entry])  # Sollte nicht raisen

    def test_invalid_enum_raises(self) -> None:
        """Ungueltiger Enum-Wert loest IngestError aus."""
        from halle_gehirn.pipeline.ingest import ManifestEntry

        entry = ManifestEntry(
            datei="test.pdf",
            titel="Test",
            doc_type="FANTASIE_TYP",
            bereich=["forschung"],
            herkunft="lehrstuhl_at",
        )
        with pytest.raises(IngestError, match="FANTASIE_TYP"):
            validate_enums([entry])


class TestDeterministicIds:
    """Tests fuer deterministische Chunk-IDs."""

    def test_same_input_same_id(self) -> None:
        """Gleiche Eingabe ergibt gleiche ID."""
        id1 = deterministic_chunk_id("abc123", 0)
        id2 = deterministic_chunk_id("abc123", 0)
        assert id1 == id2

    def test_different_input_different_id(self) -> None:
        """Verschiedene Eingaben ergeben verschiedene IDs."""
        id1 = deterministic_chunk_id("abc123", 0)
        id2 = deterministic_chunk_id("abc123", 1)
        id3 = deterministic_chunk_id("def456", 0)
        assert id1 != id2
        assert id1 != id3

    def test_id_length(self) -> None:
        """ID hat 32 Hex-Zeichen."""
        chunk_id = deterministic_chunk_id("hash", 0)
        assert len(chunk_id) == 32
        assert all(c in "0123456789abcdef" for c in chunk_id)


class TestSourceHash:
    """Tests fuer Datei-Hashing."""

    def test_hash_deterministic(self, tmp_path: Path) -> None:
        """Gleiche Datei ergibt gleichen Hash."""
        f = tmp_path / "test.txt"
        f.write_text("Hello World", encoding="utf-8")
        h1 = compute_source_hash(f)
        h2 = compute_source_hash(f)
        assert h1 == h2

    def test_hash_differs_for_different_content(self, tmp_path: Path) -> None:
        """Verschiedener Inhalt ergibt verschiedenen Hash."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("Inhalt A", encoding="utf-8")
        f2.write_text("Inhalt B", encoding="utf-8")
        assert compute_source_hash(f1) != compute_source_hash(f2)


class TestBuildChunkPayload:
    """Tests fuer ChunkPayload-Erstellung."""

    def test_payload_has_all_fields(self) -> None:
        """ChunkPayload hat alle Pflichtfelder gesetzt."""
        from halle_gehirn.pipeline.ingest import ManifestEntry

        chunk = Chunk(
            text="Testtext fuer den Chunk.",
            char_start=0,
            char_end=24,
            chunk_index=0,
            headings=["Einleitung"],
            context_prefix="Dieser Chunk beschreibt die Einleitung.",
        )
        entry = ManifestEntry(
            datei="anlagen/test.pdf",
            titel="Testdokument",
            doc_type="handbuch",
            bereich=["forschung", "infrastruktur"],
            herkunft="lehrstuhl_at",
            quelltyp="primaer",
            thema=["mensch_roboter_kollaboration"],
            anlage=["kuka_industrieroboter"],
            ansprechperson=["berger"],
            jahr=2024,
            vertraulichkeit="intern",
            status="final",
        )
        payload = build_chunk_payload(
            chunk, entry, source_hash="abc123", source_path="/test.pdf",
        )
        assert payload.text_raw == "Testtext fuer den Chunk."
        assert payload.context_prefix == "Dieser Chunk beschreibt die Einleitung."
        assert payload.text.startswith("Dieser Chunk beschreibt die Einleitung.")
        assert "Testtext fuer den Chunk." in payload.text
        assert payload.text != payload.text_raw
        assert payload.source_type == "pdf"
        assert payload.chunk_index == 0
        assert payload.source_hash == "abc123"
        assert payload.titel == "Testdokument"
        assert payload.doc_type.value == "handbuch"
        assert len(payload.bereich) == 2
        assert payload.herkunft.value == "lehrstuhl_at"
        assert payload.quelltyp.value == "primaer"
        assert payload.jahr == 2024
        assert "mensch_roboter_kollaboration" in [t.value for t in payload.thema]
        assert "kuka_industrieroboter" in payload.anlage
        assert "berger" in payload.ansprechperson
