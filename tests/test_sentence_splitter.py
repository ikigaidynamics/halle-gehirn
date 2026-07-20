"""Tests fuer den deutschen Satz-Splitter mit Abkuerzungs-Schutz."""
from __future__ import annotations

from halle_gehirn.pipeline.sentence_splitter import (
    Sentence,
    merge_list_blocks,
    split_sentences,
)


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


class TestMergeListBlocks:
    """Tests fuer merge_list_blocks() — Listen-Atomizitaet."""

    def test_consecutive_list_items_merged(self) -> None:
        """Aufeinanderfolgende Listen-Items werden zu einem Block zusammengefasst."""
        text = "- Punkt eins\n- Punkt zwei\n- Punkt drei"
        sentences = [
            Sentence(text="- Punkt eins", start=0, end=12),
            Sentence(text="- Punkt zwei", start=13, end=25),
            Sentence(text="- Punkt drei", start=26, end=38),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 1
        assert "Punkt eins" in result[0].text
        assert "Punkt drei" in result[0].text

    def test_single_list_item_not_merged(self) -> None:
        """Ein einzelnes Listen-Item bleibt unveraendert."""
        text = "Text. - Ein Punkt. Mehr Text."
        sentences = [
            Sentence(text="Text.", start=0, end=5),
            Sentence(text="- Ein Punkt.", start=6, end=18),
            Sentence(text="Mehr Text.", start=19, end=29),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 3

    def test_numbered_list_items_merged(self) -> None:
        """Nummerierte Listen-Items werden zusammengefasst."""
        text = "1. Erster\n2. Zweiter\n3. Dritter"
        sentences = [
            Sentence(text="1. Erster", start=0, end=9),
            Sentence(text="2. Zweiter", start=10, end=20),
            Sentence(text="3. Dritter", start=21, end=31),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 1

    def test_mixed_content_preserves_non_list(self) -> None:
        """Nicht-Listen-Saetze bleiben separat."""
        text = "Intro. - A\n- B\nOutro."
        sentences = [
            Sentence(text="Intro.", start=0, end=6),
            Sentence(text="- A", start=7, end=10),
            Sentence(text="- B", start=11, end=14),
            Sentence(text="Outro.", start=15, end=21),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 3  # Intro, merged list, Outro
        assert result[0].text == "Intro."
        assert result[2].text == "Outro."

    def test_empty_input(self) -> None:
        """Leere Input-Liste ergibt leere Output-Liste."""
        assert merge_list_blocks([], "") == []

    def test_letter_list_markers(self) -> None:
        """Buchstaben-Listen (a), b) etc.) werden erkannt."""
        text = "a) Punkt A\nb) Punkt B"
        sentences = [
            Sentence(text="a) Punkt A", start=0, end=10),
            Sentence(text="b) Punkt B", start=11, end=21),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 1

    def test_asterisk_list_markers(self) -> None:
        """Sternchen-Listen werden erkannt."""
        text = "* Eins\n* Zwei"
        sentences = [
            Sentence(text="* Eins", start=0, end=6),
            Sentence(text="* Zwei", start=7, end=13),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 1

    def test_offsets_correct_after_merge(self) -> None:
        """Start/End-Offsets des zusammengefassten Blocks sind korrekt."""
        text = "- Eins\n- Zwei\n- Drei"
        sentences = [
            Sentence(text="- Eins", start=0, end=6),
            Sentence(text="- Zwei", start=7, end=13),
            Sentence(text="- Drei", start=14, end=20),
        ]
        result = merge_list_blocks(sentences, text)
        assert len(result) == 1
        assert result[0].start == 0
        assert result[0].end == 20
        assert text[result[0].start : result[0].end] == text
