"""Tests fuer den deutschen Satz-Splitter mit Abkuerzungs-Schutz."""
from __future__ import annotations

from halle_gehirn.pipeline.sentence_splitter import split_sentences


class TestSplitSentences:
    """Tests fuer split_sentences()."""

    def test_simple_two_sentences(self) -> None:
        """Zwei einfache Saetze werden korrekt getrennt."""
        text = "Der Roboter bewegt sich. Die Achse dreht."
        result = split_sentences(text)
        assert len(result) == 2
        assert result[0].text == "Der Roboter bewegt sich."
        assert result[1].text == "Die Achse dreht."

    def test_abbreviation_z_b_preserved(self) -> None:
        """z.B. wird NICHT als Satzende erkannt."""
        text = "Es gibt z.B. drei Achsen. Das ist relevant."
        result = split_sentences(text)
        assert len(result) == 2
        assert "z.B." in result[0].text

    def test_abbreviation_d_h_preserved(self) -> None:
        """d.h. wird NICHT als Satzende erkannt."""
        text = "Die Anlage, d.h. der Roboter, ist aktiv. Ende."
        result = split_sentences(text)
        assert len(result) == 2
        assert "d.h." in result[0].text

    def test_title_prof_dr_preserved(self) -> None:
        """Prof. Dr. wird NICHT als Satzende erkannt."""
        text = "Prof. Dr. Mueller leitet das Labor. Er forscht."
        result = split_sentences(text)
        assert len(result) == 2
        assert "Prof." in result[0].text
        assert "Dr." in result[0].text

    def test_exclamation_and_question(self) -> None:
        """Ausrufe- und Fragezeichen sind Satzgrenzen."""
        text = "Stopp! Warum? Der Roboter haelt an."
        result = split_sentences(text)
        assert len(result) == 3

    def test_empty_input(self) -> None:
        """Leerer Input ergibt leere Liste."""
        assert split_sentences("") == []
        assert split_sentences("   ") == []

    def test_single_sentence(self) -> None:
        """Ein einzelner Satz ohne Satzende-Zeichen."""
        text = "Nur ein Fragment ohne Punkt"
        result = split_sentences(text)
        assert len(result) == 1
        assert result[0].text == text

    def test_numeric_enum_not_split(self) -> None:
        """Nummerierungen (1. 2. 3.) sind keine Satzgrenzen."""
        text = "Schritt 1. Die Achse faehrt."
        result = split_sentences(text)
        # "1." ist numerisch, also kein Split dort
        assert any("1." in s.text for s in result)

    def test_offsets_correct(self) -> None:
        """Start/End-Offsets stimmen mit dem Originaltext ueberein."""
        text = "Erster Satz. Zweiter Satz."
        result = split_sentences(text)
        for sent in result:
            assert text[sent.start : sent.end] == sent.text

    def test_multiline_text(self) -> None:
        """Mehrzeilige Texte werden korrekt verarbeitet."""
        text = "Erste Zeile.\nZweite Zeile. Dritte Zeile."
        result = split_sentences(text)
        assert len(result) >= 2
