"""Tests fuer die automatische Metadaten-Erkennung."""
from __future__ import annotations

from halle_gehirn.extraction.metadata_detector import (
    MetadataSuggestion,
    _detect_doc_type_and_grad,
    _detect_registry_facets,
    _detect_year,
    detect_metadata,
    extract_text_from_upload,
)

# ── Gemeinsame Test-Choices (Vokabular) ──

_CHOICES: dict[str, dict[str, str]] = {
    "doc_type": {"abschlussarbeit": "Abschlussarbeit", "handbuch": "Handbuch"},
    "bereich": {"forschung": "Forschung", "lehre": "Lehre"},
    "herkunft": {"lehrstuhl_at": "Lehrstuhl AT"},
    "quelltyp": {"primaer": "Primär"},
    "vertraulichkeit": {"intern": "Intern"},
    "status": {"final": "Final"},
    "grad": {"master": "Master", "bachelor": "Bachelor"},
    "thema": {
        "mensch_roboter_kollaboration": "Mensch-Roboter-Kollaboration",
        "vernetzte_steuerungstechnik": "Vernetzte Steuerungstechnik",
    },
    "anlage": {
        "greifroboter": "Greifroboter (Modellfabrik)",
        "kuka_industrieroboter": "KUKA-Industrieroboter (Roboterlabor)",
    },
    "projekt": {
        "direct": "DIRECT — Forschungsprojekt",
    },
    "ansprechperson": {
        "bork": "Christian Bork",
        "jost": "Robin Jost",
    },
}


# ── _detect_year ──


class TestDetectYear:
    def test_year_from_filename(self) -> None:
        assert _detect_year("2024_mustermann_thesis.pdf", "") == 2024

    def test_year_from_text(self) -> None:
        assert _detect_year("thesis.pdf", "Eingereicht im Jahr 2023 am") == 2023

    def test_filename_priority(self) -> None:
        assert _detect_year("2024_doc.pdf", "Im Jahr 2019 wurde") == 2024

    def test_no_year(self) -> None:
        assert _detect_year("dokument.pdf", "Kein Jahr hier") is None

    def test_future_year_rejected(self) -> None:
        assert _detect_year("2099_doc.pdf", "") is None

    def test_old_year_rejected(self) -> None:
        assert _detect_year("1899_doc.pdf", "") is None


# ── _detect_doc_type_and_grad ──


class TestDetectDocType:
    def test_masterarbeit(self) -> None:
        dt, grad = _detect_doc_type_and_grad(
            "Masterarbeit_Schmidt.pdf", "",
        )
        assert dt == "abschlussarbeit"
        assert grad == "master"

    def test_bachelorarbeit_in_text(self) -> None:
        dt, grad = _detect_doc_type_and_grad(
            "thesis.pdf", "Dies ist eine Bachelorarbeit.",
        )
        assert dt == "abschlussarbeit"
        assert grad == "bachelor"

    def test_handbuch(self) -> None:
        dt, grad = _detect_doc_type_and_grad("Handbuch_KUKA.pdf", "")
        assert dt == "handbuch"
        assert grad is None

    def test_projektbericht(self) -> None:
        dt, grad = _detect_doc_type_and_grad(
            "report.pdf", "Projektbericht zum Thema",
        )
        assert dt == "projektbericht"
        assert grad is None

    def test_no_match(self) -> None:
        dt, grad = _detect_doc_type_and_grad("data.pdf", "Allgemeiner Text")
        assert dt is None
        assert grad is None


# ── _detect_registry_facets ──


class TestDetectRegistryFacets:
    def test_matches_anlage_label(self) -> None:
        result = _detect_registry_facets(
            "doc.pdf",
            "Arbeit am Greifroboter (Modellfabrik) und KUKA",
            _CHOICES,
        )
        assert "greifroboter" in result.get("anlage", [])

    def test_matches_slug(self) -> None:
        result = _detect_registry_facets(
            "greifroboter_doku.pdf", "", _CHOICES,
        )
        assert "greifroboter" in result.get("anlage", [])

    def test_matches_ansprechperson(self) -> None:
        result = _detect_registry_facets(
            "doc.pdf", "Betreuer: Christian Bork", _CHOICES,
        )
        assert "bork" in result.get("ansprechperson", [])

    def test_matches_projekt(self) -> None:
        result = _detect_registry_facets(
            "doc.pdf", "Im Rahmen von DIRECT", _CHOICES,
        )
        assert "direct" in result.get("projekt", [])

    def test_no_false_positive(self) -> None:
        result = _detect_registry_facets(
            "random.pdf", "Nichts Relevantes hier", _CHOICES,
        )
        assert result.get("anlage", []) == []
        assert result.get("thema", []) == []


# ── detect_metadata (Integration) ──


class TestDetectMetadata:
    def test_full_masterarbeit(self) -> None:
        sug = detect_metadata(
            "2024_mueller_greifroboter_masterarbeit.pdf",
            "Masterarbeit: Bahnplanung fuer den Greifroboter",
            _CHOICES,
        )
        assert sug.titel  # non-empty
        assert sug.jahr == 2024
        assert sug.doc_type == "abschlussarbeit"
        assert sug.grad == "master"
        assert sug.sorte == "abschlussarbeiten"
        assert "lehre" in sug.bereich
        assert "greifroboter" in sug.anlage

    def test_defaults_no_match(self) -> None:
        sug = detect_metadata("random.pdf", "", _CHOICES)
        assert sug.herkunft == "lehrstuhl_at"
        assert sug.quelltyp == "primaer"
        assert sug.vertraulichkeit == "intern"
        assert sug.status == "final"
        assert sug.doc_type is None
        assert sug.jahr is None


# ── extract_text_from_upload ──


class TestExtractTextFromUpload:
    def test_txt_file(self) -> None:
        data = "Hallo Welt".encode("utf-8")
        result = extract_text_from_upload(data, "test.txt")
        assert "Hallo Welt" in result

    def test_md_file(self) -> None:
        data = "# Titel\n\nInhalt hier".encode("utf-8")
        result = extract_text_from_upload(data, "doc.md")
        assert "Titel" in result

    def test_latin1_fallback(self) -> None:
        data = "Stra\xdfe".encode("latin-1")
        result = extract_text_from_upload(data, "doc.txt")
        assert "Straße" in result
