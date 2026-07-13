"""Tests fuer halle_gehirn.manifest.editor.

Prueft: load_vokabular_choices (echte Slugs), save_manifest_entry
(anhaengen ohne Zerstoerung), validate_entry (ablehnen/akzeptieren).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from halle_gehirn.manifest.editor import (
    list_manifest_entries,
    load_manifest_entries,
    load_vokabular_choices,
    save_manifest_entry,
    save_uploaded_file,
    save_vokabular_entry,
    validate_entry,
)
from halle_gehirn.pipeline.ingest import ManifestEntry

# ────────────────────────── Fixtures ──────────────────────────

_MINIMAL_MANIFEST = """\
dokumente:
  - datei: "transfer/test.pdf"
    titel: "Testdokument"
    doc_type: flyer
    bereich: [transfer]
    herkunft: mdz
    quelltyp: primaer
    vertraulichkeit: offen
"""

_MINIMAL_VOKABULAR = """\
thema:
  mensch_roboter_kollaboration: "MRK"
  vernetzte_steuerungstechnik: "VST"
anlage:
  ur10e: "UR10e"
  greifroboter: "Greifroboter"
projekt:
  direct: "DIRECT"
ansprechperson:
  berger: "Prof. Berger"
"""


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Erstellt ein temporaeres data/-Verzeichnis mit Manifest + Vokabular."""
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(_MINIMAL_MANIFEST, encoding="utf-8")
    vokabular = tmp_path / "vokabular.yaml"
    vokabular.write_text(_MINIMAL_VOKABULAR, encoding="utf-8")
    # Sorten-Verzeichnisse
    for sorte in ("anlagen", "transfer", "abschlussarbeiten"):
        (tmp_path / "manual" / sorte).mkdir(parents=True)
    return tmp_path


def _valid_entry(datei: str = "anlagen/neu.pdf") -> ManifestEntry:
    """Erzeugt einen gueltigen ManifestEntry fuer Tests."""
    return ManifestEntry(
        datei=datei,
        titel="Neues Handbuch",
        doc_type="handbuch",
        bereich=["infrastruktur"],
        herkunft="extern",
        quelltyp="primaer",
        thema=["vernetzte_steuerungstechnik"],
        anlage=["ur10e"],
        vertraulichkeit="intern",
        status="final",
    )


# ────────────────────────── load_vokabular_choices ──────────────────────────


class TestLoadVokabularChoices:
    """Tests fuer load_vokabular_choices()."""

    def test_returns_enum_slugs(self, data_dir: Path) -> None:
        """Enum-Facetten enthalten echte Werte aus schema.py."""
        choices = load_vokabular_choices(data_dir / "vokabular.yaml")
        assert "transfer" in choices["bereich"]
        assert "handbuch" in choices["doc_type"]
        assert "primaer" in choices["quelltyp"]
        assert "lehrstuhl_at" in choices["herkunft"]
        assert "offen" in choices["vertraulichkeit"]
        assert "final" in choices["status"]
        assert "master" in choices["grad"]

    def test_returns_registry_slugs(self, data_dir: Path) -> None:
        """Registry-Facetten enthalten Slugs aus vokabular.yaml."""
        choices = load_vokabular_choices(data_dir / "vokabular.yaml")
        assert "mensch_roboter_kollaboration" in choices["thema"]
        assert "ur10e" in choices["anlage"]
        assert "direct" in choices["projekt"]
        assert "berger" in choices["ansprechperson"]

    def test_registry_labels(self, data_dir: Path) -> None:
        """Registry-Eintraege haben menschenlesbare Labels."""
        choices = load_vokabular_choices(data_dir / "vokabular.yaml")
        assert choices["anlage"]["ur10e"] == "UR10e"
        assert choices["thema"]["mensch_roboter_kollaboration"] == "MRK"


# ────────────────────────── save_manifest_entry ──────────────────────────


class TestSaveManifestEntry:
    """Tests fuer save_manifest_entry()."""

    def test_appends_without_destroying_existing(self, data_dir: Path) -> None:
        """Neuer Eintrag wird angehaengt, Bestehende bleiben erhalten."""
        manifest_path = data_dir / "manifest.yaml"
        original = load_manifest_entries(manifest_path)
        assert len(original) == 1

        save_manifest_entry(_valid_entry(), manifest_path)

        updated = load_manifest_entries(manifest_path)
        assert len(updated) == 2
        assert updated[0].datei == "transfer/test.pdf"
        assert updated[1].datei == "anlagen/neu.pdf"
        assert updated[1].titel == "Neues Handbuch"

    def test_result_is_valid_yaml(self, data_dir: Path) -> None:
        """Gespeicherte Datei ist gueltiges YAML."""
        manifest_path = data_dir / "manifest.yaml"
        save_manifest_entry(_valid_entry(), manifest_path)

        content = manifest_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(content)
        assert "dokumente" in parsed
        assert len(parsed["dokumente"]) == 2

    def test_preserves_comments(self, data_dir: Path) -> None:
        """Kommentare im Original bleiben erhalten (Append-Strategie)."""
        manifest_path = data_dir / "manifest.yaml"
        # Kommentar manuell einfuegen
        content = manifest_path.read_text(encoding="utf-8")
        content = "# Kommentar bleibt\n" + content
        manifest_path.write_text(content, encoding="utf-8")

        save_manifest_entry(_valid_entry(), manifest_path)

        result = manifest_path.read_text(encoding="utf-8")
        assert "# Kommentar bleibt" in result

    def test_lists_in_flow_style(self, data_dir: Path) -> None:
        """Listen werden im Flow-Style geschrieben: [wert1, wert2]."""
        manifest_path = data_dir / "manifest.yaml"
        entry = _valid_entry()
        entry.bereich = ["infrastruktur", "forschung"]
        save_manifest_entry(entry, manifest_path)

        content = manifest_path.read_text(encoding="utf-8")
        assert "bereich: [infrastruktur, forschung]" in content


# ────────────────────────── validate_entry ──────────────────────────


class TestValidateEntry:
    """Tests fuer validate_entry()."""

    def test_accepts_valid_entry(self, data_dir: Path) -> None:
        """Gueltiger Eintrag erzeugt keine Fehler."""
        errors = validate_entry(
            _valid_entry(), data_dir / "vokabular.yaml"
        )
        assert errors == []

    def test_rejects_invalid_anlage_slug(self, data_dir: Path) -> None:
        """Unbekannter anlage-Slug wird abgelehnt."""
        entry = _valid_entry()
        entry.anlage = ["gibt_es_nicht"]
        errors = validate_entry(entry, data_dir / "vokabular.yaml")
        assert any("gibt_es_nicht" in e for e in errors)

    def test_rejects_invalid_doc_type(self, data_dir: Path) -> None:
        """Ungueltiger doc_type-Enum-Wert wird abgelehnt."""
        entry = _valid_entry()
        entry.doc_type = "ungueltig"
        errors = validate_entry(entry, data_dir / "vokabular.yaml")
        assert any("doc_type" in e for e in errors)

    def test_rejects_empty_pflichtfelder(self) -> None:
        """Leere Pflichtfelder werden erkannt."""
        entry = ManifestEntry(
            datei="",
            titel="",
            doc_type="",
            bereich=[],
            herkunft="",
            vertraulichkeit="",
        )
        errors = validate_entry(entry)
        assert len(errors) >= 4  # datei, titel, doc_type, bereich, ...


# ────────────────────────── list_manifest_entries ──────────────────────────


class TestListManifestEntries:
    """Tests fuer list_manifest_entries()."""

    def test_returns_display_dicts(self, data_dir: Path) -> None:
        """Gibt Dicts mit menschenlesbaren Labels zurueck."""
        rows = list_manifest_entries(data_dir / "manifest.yaml")
        assert len(rows) == 1
        row = rows[0]
        assert row["datei"] == "transfer/test.pdf"
        assert row["titel"] == "Testdokument"
        assert "Transfer" in row["bereich"]
        assert row["doc_type"] == "Flyer"
        assert row["vertraulichkeit"] == "Offen"


# ────────────────────────── save_uploaded_file ──────────────────────────


class TestSaveUploadedFile:
    """Tests fuer save_uploaded_file()."""

    def test_saves_file(self, data_dir: Path) -> None:
        """Datei wird korrekt gespeichert."""
        manual = data_dir / "manual"
        path = save_uploaded_file(b"PDF content", "test.pdf", "anlagen", manual)
        assert path.exists()
        assert path.read_bytes() == b"PDF content"

    def test_rejects_existing_file(self, data_dir: Path) -> None:
        """Existierende Datei wird nicht ueberschrieben."""
        manual = data_dir / "manual"
        (manual / "anlagen" / "test.pdf").write_bytes(b"existing")
        with pytest.raises(FileExistsError):
            save_uploaded_file(b"new", "test.pdf", "anlagen", manual)

    def test_rejects_unknown_sorte(self, data_dir: Path) -> None:
        """Unbekannte Sorte wird abgelehnt."""
        manual = data_dir / "manual"
        with pytest.raises(ValueError, match="Unbekannte Sorte"):
            save_uploaded_file(b"data", "test.pdf", "gibts_nicht", manual)


# ────────────────────────── save_vokabular_entry ──────────────────────────


class TestSaveVokabularEntry:
    """Tests fuer save_vokabular_entry()."""

    def test_adds_entry_to_section(self, data_dir: Path) -> None:
        """Neuer Slug wird in der richtigen Sektion eingefuegt."""
        vok = data_dir / "vokabular.yaml"
        save_vokabular_entry("anlage", "neuer_roboter", "Neuer Roboter XY", vok)

        raw = yaml.safe_load(vok.read_text(encoding="utf-8"))
        assert "neuer_roboter" in raw["anlage"]
        assert raw["anlage"]["neuer_roboter"] == "Neuer Roboter XY"

    def test_preserves_existing_entries(self, data_dir: Path) -> None:
        """Bestehende Eintraege bleiben erhalten."""
        vok = data_dir / "vokabular.yaml"
        save_vokabular_entry("anlage", "neuer_roboter", "Neuer Roboter", vok)

        raw = yaml.safe_load(vok.read_text(encoding="utf-8"))
        assert "ur10e" in raw["anlage"]
        assert "greifroboter" in raw["anlage"]
        assert "neuer_roboter" in raw["anlage"]

    def test_preserves_comments(self, data_dir: Path) -> None:
        """Kommentare in vokabular.yaml bleiben erhalten."""
        vok = data_dir / "vokabular.yaml"
        content = "# Kopfkommentar\n" + vok.read_text(encoding="utf-8")
        vok.write_text(content, encoding="utf-8")

        save_vokabular_entry("projekt", "neues_projekt", "Neues Projekt", vok)

        result = vok.read_text(encoding="utf-8")
        assert "# Kopfkommentar" in result

    def test_rejects_duplicate_slug(self, data_dir: Path) -> None:
        """Duplikat-Slug wird abgelehnt."""
        vok = data_dir / "vokabular.yaml"
        with pytest.raises(ValueError, match="existiert bereits"):
            save_vokabular_entry("anlage", "ur10e", "Duplikat", vok)

    def test_rejects_invalid_slug(self, data_dir: Path) -> None:
        """Ungueltiger Slug (Grossbuchstaben, Sonderzeichen) wird abgelehnt."""
        vok = data_dir / "vokabular.yaml"
        with pytest.raises(ValueError, match="Ungültiger Slug"):
            save_vokabular_entry("anlage", "Mein-Roboter", "Label", vok)

    def test_rejects_unknown_facet(self, data_dir: Path) -> None:
        """Unbekannte Facette wird abgelehnt."""
        vok = data_dir / "vokabular.yaml"
        with pytest.raises(ValueError, match="Unbekannte Facette"):
            save_vokabular_entry("gibts_nicht", "slug", "Label", vok)

    def test_result_is_valid_yaml(self, data_dir: Path) -> None:
        """Ergebnis ist gueltiges YAML nach Einfuegung."""
        vok = data_dir / "vokabular.yaml"
        save_vokabular_entry("thema", "neues_thema", "Neues Thema", vok)
        save_vokabular_entry("ansprechperson", "mueller", "Dr. Müller", vok)

        raw = yaml.safe_load(vok.read_text(encoding="utf-8"))
        assert raw["thema"]["neues_thema"] == "Neues Thema"
        assert raw["ansprechperson"]["mueller"] == "Dr. Müller"

    def test_choices_reflect_new_entry(self, data_dir: Path) -> None:
        """load_vokabular_choices zeigt neuen Eintrag nach Speichern."""
        vok = data_dir / "vokabular.yaml"
        save_vokabular_entry("anlage", "neuer_roboter", "Neuer Roboter", vok)

        choices = load_vokabular_choices(vok)
        assert "neuer_roboter" in choices["anlage"]
        assert choices["anlage"]["neuer_roboter"] == "Neuer Roboter"
