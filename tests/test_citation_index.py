"""Tests fuer den Zitations-Index aus Literaturverzeichnissen."""
from __future__ import annotations

from halle_gehirn.extraction.citation_index import parse_citations


class TestParseCitations:
    """Tests fuer parse_citations()."""

    def test_bracket_format(self) -> None:
        """[N] Format wird korrekt geparst."""
        body = (
            "## 1 Einleitung\n\nText.\n\n"
            "## Literaturverzeichnis\n\n"
            "[1] Mueller, K.: Industrieroboter, 2023.\n"
            "[2] Schmidt, H.: Steuerungstechnik, 2022.\n"
            "[3] Berger, T.: KI in der Produktion, 2024.\n"
        )
        result = parse_citations(body)
        assert len(result) == 3
        assert "Mueller" in result["1"]
        assert "Schmidt" in result["2"]
        assert "Berger" in result["3"]

    def test_dot_format(self) -> None:
        """N. Format wird korrekt geparst."""
        body = (
            "## Quellenverzeichnis\n\n"
            "1. Mueller, K.: Industrieroboter, 2023.\n"
            "2. Schmidt, H.: Steuerungstechnik, 2022.\n"
        )
        result = parse_citations(body)
        assert len(result) == 2
        assert "Mueller" in result["1"]

    def test_parenthesis_format(self) -> None:
        """(N) Format wird korrekt geparst."""
        body = (
            "## Literatur\n\n"
            "(1) Mueller, K.: Industrieroboter, 2023.\n"
            "(2) Schmidt, H.: Steuerungstechnik, 2022.\n"
        )
        result = parse_citations(body)
        assert len(result) == 2
        assert "Mueller" in result["1"]

    def test_multiline_entry(self) -> None:
        """Mehrzeilige Eintraege werden akkumuliert."""
        body = (
            "## Literaturverzeichnis\n\n"
            "[1] Mueller, K.; Schmidt, H.: Ein langer Titel\n"
            "    ueber mehrere Zeilen. Verlag, 2023.\n"
            "[2] Berger, T.: Kurzer Eintrag, 2024.\n"
        )
        result = parse_citations(body)
        assert len(result) == 2
        assert "mehrere Zeilen" in result["1"]
        assert "Berger" in result["2"]

    def test_no_bib_section(self) -> None:
        """Ohne Literaturverzeichnis-Section wird leeres dict zurueckgegeben."""
        body = "## 1 Einleitung\n\nText ohne Literatur.\n\n## 2 Methode\n\nText."
        result = parse_citations(body)
        assert result == {}

    def test_empty_input(self) -> None:
        """Leerer Input ergibt leeres dict."""
        assert parse_citations("") == {}

    def test_section_ends_at_next_heading(self) -> None:
        """Die Literaturverzeichnis-Section endet beim naechsten Heading."""
        body = (
            "## Literaturverzeichnis\n\n"
            "[1] Mueller, K.: Erster Eintrag, 2023.\n\n"
            "## Anhang\n\n"
            "[2] Schmidt, H.: Nicht im Literaturverzeichnis.\n"
        )
        result = parse_citations(body)
        assert len(result) == 1
        assert "1" in result

    def test_numbered_heading(self) -> None:
        """Nummerierte Headings werden korrekt erkannt."""
        body = (
            "## 7 Literaturverzeichnis\n\n"
            "[1] Mueller, K.: Robotik, 2023.\n"
        )
        result = parse_citations(body)
        assert len(result) == 1

    def test_alternative_headings(self) -> None:
        """Verschiedene Heading-Varianten werden erkannt."""
        for heading in [
            "References", "Bibliography", "Quellen", "Quellenangaben",
        ]:
            body = f"## {heading}\n\n[1] Test Reference, 2023.\n"
            result = parse_citations(body)
            assert len(result) >= 1, f"Heading '{heading}' nicht erkannt"

    def test_bracket_format_preferred_over_alt(self) -> None:
        """[N] Format wird bevorzugt, wenn vorhanden."""
        body = (
            "## Literaturverzeichnis\n\n"
            "[1] Mueller via bracket.\n"
            "[2] Schmidt via bracket.\n"
        )
        result = parse_citations(body)
        assert len(result) == 2
        assert "bracket" in result["1"]
