"""Tests fuer die Glossar-Extraktion aus Abkuerzungsverzeichnissen."""
from __future__ import annotations

from halle_gehirn.extraction.glossar import parse_glossar


class TestParseGlossar:
    """Tests fuer parse_glossar()."""

    def test_basic_em_dash_entries(self) -> None:
        """Eintraege mit EM-DASH Trennzeichen werden erkannt."""
        body = (
            "## Einleitung\n\nText.\n\n"
            "## Abkuerzungsverzeichnis\n\n"
            "AES \u2014 Advanced Encryption Standard\n"
            "TCP \u2014 Tool Center Point\n"
            "MRK \u2014 Mensch-Roboter-Kollaboration\n\n"
            "## 1 Einleitung\n\nWeiterer Text."
        )
        result = parse_glossar(body)
        assert len(result) == 3
        assert result["AES"] == "Advanced Encryption Standard"
        assert result["TCP"] == "Tool Center Point"
        assert result["MRK"] == "Mensch-Roboter-Kollaboration"

    def test_hyphen_separator(self) -> None:
        """Eintraege mit Bindestrich-Trennzeichen werden erkannt."""
        body = (
            "## Abkuerzungen\n\n"
            "ISO - International Organization for Standardization\n"
            "DIN - Deutsches Institut fuer Normung\n"
        )
        result = parse_glossar(body)
        assert len(result) == 2
        assert result["ISO"] == "International Organization for Standardization"

    def test_colon_separator(self) -> None:
        """Eintraege mit Doppelpunkt-Trennzeichen werden erkannt."""
        body = (
            "## Glossar\n\n"
            "TCP: Tool Center Point\n"
            "MRK: Mensch-Roboter-Kollaboration\n"
        )
        result = parse_glossar(body)
        assert len(result) == 2
        assert result["TCP"] == "Tool Center Point"

    def test_tab_separated_entries(self) -> None:
        """Tab-getrennte Eintraege werden erkannt."""
        body = (
            "## Abkuerzungsverzeichnis\n\n"
            "AES\t\tAdvanced Encryption Standard\n"
            "TCP\t\tTool Center Point\n"
        )
        result = parse_glossar(body)
        assert len(result) == 2
        assert result["AES"] == "Advanced Encryption Standard"

    def test_no_glossar_section(self) -> None:
        """Ohne Abkuerzungsverzeichnis-Section wird leeres dict zurueckgegeben."""
        body = "## 1 Einleitung\n\nText ohne Glossar.\n\n## 2 Methode\n\nText."
        result = parse_glossar(body)
        assert result == {}

    def test_empty_glossar_section(self) -> None:
        """Leere Glossar-Section ergibt leeres dict."""
        body = (
            "## Abkuerzungsverzeichnis\n\n"
            "Keine Eintraege hier.\n\n"
            "## 1 Einleitung\n\nText."
        )
        result = parse_glossar(body)
        assert result == {}

    def test_numbered_heading(self) -> None:
        """Nummerierte Headings werden korrekt erkannt (z.B. '3 Abkuerzungsverzeichnis')."""
        body = (
            "## 3 Abkuerzungsverzeichnis\n\n"
            "TCP - Tool Center Point\n"
            "MRK - Mensch-Roboter-Kollaboration\n\n"
            "## 4 Einleitung\n\nText."
        )
        result = parse_glossar(body)
        assert len(result) == 2

    def test_alternative_heading_names(self) -> None:
        """Verschiedene Heading-Varianten werden erkannt."""
        for heading in ["Glossary", "Abbreviations", "Symbole und Abkuerzungen"]:
            body = f"## {heading}\n\nAES - Advanced Encryption Standard\n"
            result = parse_glossar(body)
            assert len(result) >= 1, f"Heading '{heading}' nicht erkannt"

    def test_section_ends_at_next_heading(self) -> None:
        """Die Glossar-Section endet beim naechsten Heading."""
        body = (
            "## Abkuerzungsverzeichnis\n\n"
            "AES - Advanced Encryption Standard\n\n"
            "## 1 Einleitung\n\n"
            "TCP - Transmission Control Protocol\n"  # Nicht in Glossar-Section
        )
        result = parse_glossar(body)
        assert len(result) == 1
        assert "AES" in result
        assert "TCP" not in result

    def test_empty_input(self) -> None:
        """Leerer Input ergibt leeres dict."""
        assert parse_glossar("") == {}

    def test_key_length_limit(self) -> None:
        """Akronyme ueber 30 Zeichen werden ignoriert."""
        body = (
            "## Abkuerzungsverzeichnis\n\n"
            "A" * 31 + " - Langform\n"
            "OK - Gueltig\n"
        )
        result = parse_glossar(body)
        assert "OK" in result
        # Das zu lange Akronym soll nicht enthalten sein
        assert all(len(k) <= 30 for k in result)

    def test_en_dash_separator(self) -> None:
        """Eintraege mit EN-DASH Trennzeichen werden erkannt."""
        body = (
            "## Abkuerzungsverzeichnis\n\n"
            "TCP \u2013 Tool Center Point\n"
        )
        result = parse_glossar(body)
        assert len(result) == 1
        assert result["TCP"] == "Tool Center Point"
