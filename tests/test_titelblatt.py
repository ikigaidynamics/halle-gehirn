"""Tests fuer WP4: BTU-Titelblatt-Parser + Metadaten-Integration.

Drei synthetische BTU-Titelblatt-Varianten (klassisch, mit Labels,
englisch angehaucht) plus Integration in detect_metadata:
Registry-Matching, Vorschlaege fuer Unbekannte, Datums-Vorrang.
Matrikelnummern werden bewusst NICHT extrahiert (DSGVO).
"""
from __future__ import annotations

from typing import ClassVar

from halle_gehirn.extraction.metadata_detector import detect_metadata
from halle_gehirn.extraction.titelblatt import (
    nachname_slug,
    parse_titelblatt,
)

# Variante 1: klassisches BTU-Titelblatt ("vorgelegt von")
_TITELBLATT_KLASSISCH = """\
Brandenburgische Technische Universitaet Cottbus-Senftenberg
Fakultaet 3 — Maschinenbau, Elektro- und Energiesysteme
Lehrstuhl KI-gestuetzte Automatisierungstechnik

Masterarbeit

Optimierung der Bahnplanung eines Industrieroboters

vorgelegt von: Zhili Wang
Matrikelnummer: 4123456
Studiengang: Elektrotechnik

Betreuer: M. Eng. Erik Lautsch
1. Gutachter: Prof. Dr.-Ing. Kim Berger
2. Gutachter: Dr. rer. nat. Anna Schulze

Cottbus, den 15.03.2025
"""

# Variante 2: Labels statt "vorgelegt von"
_TITELBLATT_LABELS = """\
BTU Cottbus-Senftenberg

Bachelorarbeit im Studiengang Maschinenbau

Autor: Alexander Ruhs
Erstgutachter: Prof. Dr. Kim Berger
Zweitgutachterin: Dr. Maria Krause

eingereicht am 02.11.2024
"""

# Variante 3: "eingereicht von Frau", Pruefer-Schreibweise
_TITELBLATT_FRAU = """\
Weiterentwicklung von Datenhandschuhen

eingereicht von Frau Erika Musterfrau
Pruefer: Prof. Dr. Kim Berger

Senftenberg, 01.07.2025
"""


class TestParseTitelblatt:
    """Regelbasierter Parser auf den drei Varianten."""

    def test_klassisch_alle_felder(self) -> None:
        """Variante 1: Autor, 3 Betreuer, Studiengang, Jahr."""
        info = parse_titelblatt(_TITELBLATT_KLASSISCH)
        assert info.autor == "Zhili Wang"
        assert info.betreuer == ["Erik Lautsch", "Kim Berger", "Anna Schulze"]
        assert info.studiengang == "Elektrotechnik"
        assert info.jahr == 2025

    def test_labels_variante(self) -> None:
        """Variante 2: Autor-Label, Erst-/Zweitgutachter, Datum im Text."""
        info = parse_titelblatt(_TITELBLATT_LABELS)
        assert info.autor == "Alexander Ruhs"
        assert info.betreuer == ["Kim Berger", "Maria Krause"]
        assert info.studiengang == "Maschinenbau"
        assert info.jahr == 2024

    def test_frau_und_pruefer(self) -> None:
        """Variante 3: 'eingereicht von Frau', Pruefer ohne Umlaut."""
        info = parse_titelblatt(_TITELBLATT_FRAU)
        assert info.autor == "Erika Musterfrau"
        assert info.betreuer == ["Kim Berger"]
        assert info.jahr == 2025

    def test_keine_matrikelnummer_im_ergebnis(self) -> None:
        """DSGVO: Matrikelnummer taucht nirgends im Ergebnis auf."""
        info = parse_titelblatt(_TITELBLATT_KLASSISCH)
        as_text = f"{info.autor} {info.betreuer} {info.studiengang} {info.jahr}"
        assert "4123456" not in as_text

    def test_leerer_text(self) -> None:
        """Leerer Text liefert leere Info statt Fehler."""
        info = parse_titelblatt("")
        assert info.autor is None
        assert info.betreuer == []
        assert info.jahr is None


class TestNachnameSlug:
    """Slug-Ableitung (Nachname, lowercase, Umlaut-Transliteration)."""

    def test_simple_name(self) -> None:
        assert nachname_slug("Kim Berger") == "berger"

    def test_with_titles(self) -> None:
        assert nachname_slug("Prof. Dr.-Ing. habil. Kim Berger") == "berger"

    def test_umlaut_transliteration(self) -> None:
        assert nachname_slug("Jana Schroeder-Müller") == "schroeder-mueller"

    def test_empty(self) -> None:
        assert nachname_slug("") == ""


class TestDetectMetadataIntegration:
    """Integration: Registry-Matching + Vorschlaege + Datums-Vorrang."""

    _CHOICES: ClassVar[dict[str, dict[str, str]]] = {
        "thema": {},
        "anlage": {},
        "projekt": {},
        "ansprechperson": {
            "berger": "Prof. Berger",
            "lautsch": "Erik Lautsch",
        },
        "autor": {"wang": "Zhili Wang"},
    }

    def test_known_persons_matched_to_slugs(self) -> None:
        """Bekannte Personen landen als Slugs, Unbekannte als Vorschlag."""
        sug = detect_metadata(
            "Masterarbeit_Wang.pdf", _TITELBLATT_KLASSISCH, self._CHOICES,
        )
        assert sug.autor == ["wang"]
        assert sug.autor_vorschlag is None
        assert "berger" in sug.ansprechperson
        assert "lautsch" in sug.ansprechperson
        assert sug.ansprechperson_vorschlag == ["Anna Schulze"]
        assert sug.studiengang == "Elektrotechnik"

    def test_unknown_autor_becomes_vorschlag(self) -> None:
        """Unbekannter Autor wird als Klartext-Vorschlag gemeldet."""
        sug = detect_metadata(
            "Bachelorarbeit.pdf", _TITELBLATT_LABELS, self._CHOICES,
        )
        assert sug.autor == []
        assert sug.autor_vorschlag == "Alexander Ruhs"

    def test_titelblatt_datum_beats_first_year(self) -> None:
        """Datum auf dem Titelblatt schlaegt die Erste-Jahreszahl-Heuristik.

        'ISO 9283:1998' steht VOR dem Abgabedatum — die alte Heuristik
        haette 1998 geliefert.
        """
        text = (
            "Messung nach ISO 9283:1998 Standard\n\n"
            "Masterarbeit\n\nvorgelegt von: Max Muster\n\n"
            "Cottbus, den 10.09.2025\n"
        )
        sug = detect_metadata("arbeit.pdf", text, self._CHOICES)
        assert sug.jahr == 2025

    def test_doc_type_detection_still_works(self) -> None:
        """Bestehende doc_type/grad-Erkennung bleibt unveraendert."""
        sug = detect_metadata(
            "Masterarbeit_Wang.pdf", _TITELBLATT_KLASSISCH, self._CHOICES,
        )
        assert sug.doc_type == "abschlussarbeit"
        assert sug.grad == "master"
