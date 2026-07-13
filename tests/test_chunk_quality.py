"""Chunk-Qualitaets-Test auf einem realistischen deutschen Korpus.

Baut ein repraesentatives Abschlussarbeit-Dokument (Front-Matter,
nummerierte Kapitel, ueberlange Section, technische Tabelle, Tail-Matter),
laesst es durch Chunker + Filter laufen und prueft harte Qualitaets-
Invarianten sowie aggregierte Qualitaetsbaender ueber ``evaluate_chunks``.

Die Korpus-Baufunktion wird auch vom Report-Skript
``scripts/eval_chunk_quality.py`` importiert (eine Quelle der Wahrheit).
"""
from __future__ import annotations

import pytest

from halle_gehirn.config import get_settings
from halle_gehirn.eval.chunk_quality import QualityThresholds, evaluate_chunks
from halle_gehirn.extraction.base import ExtractedDoc, TableBlock
from halle_gehirn.pipeline.chunk_filter import filter_chunks
from halle_gehirn.pipeline.chunker import Chunk, MarkdownChunker, count_tokens

# ── Repraesentativer Korpus (Abschlussarbeit) ──

_LONG_SENTENCES = [
    f"Die Achse {i} des Sechsachsroboters wurde bei einer Vorschub"
    f"geschwindigkeit von {40 + i} Prozent vermessen, wobei die "
    f"Wiederholgenauigkeit nach ISO 9283 im Rahmen der Toleranz blieb."
    for i in range(90)
]


def _oversized_table() -> TableBlock:
    """Technische Messtabelle, die ueber das Token-Limit hinausgeht."""
    header = "| Messpunkt | Sollwert [mm] | Istwert [mm] | Abweichung [mm] |"
    sep = "|---|---|---|---|"
    rows = [
        f"| P{i:03d} | {100 + i}.0 | {100 + i}.{i % 9} | 0.{i % 9} |"
        for i in range(160)
    ]
    return TableBlock(markdown="\n".join([header, sep, *rows]), page=7)


def build_abschlussarbeit() -> ExtractedDoc:
    """Baut ein repraesentatives Abschlussarbeit-ExtractedDoc.

    Enthaelt bewusst Front-Matter (Titel + Inhaltsverzeichnis),
    nummerierte Kapitel mit deutschem Fliesstext, eine ueberlange Section
    (erzwingt Satz-Split), eine ueberlange Tabelle (erzwingt Tabellen-Split)
    und Tail-Matter (Literaturverzeichnis + Eidesstattliche Erklaerung).
    """
    long_body = " ".join(_LONG_SENTENCES)
    body = (
        "# Masterarbeit\n\n"
        "Optimierung der Bahnplanung eines Industrieroboters in der "
        "Modellfabrik des Lehrstuhls KI-gestuetzte Automatisierungstechnik.\n\n"
        "## Inhaltsverzeichnis\n\n"
        "1 Einleitung ......... 1\n"
        "2 Grundlagen ......... 4\n"
        "3 Methodik ......... 12\n\n"
        "## 1 Einleitung\n\n"
        "Die Automatisierung der Modellfabrik stellt hohe Anforderungen an "
        "die Bahnplanung. Ziel dieser Arbeit ist die Reduktion der "
        "Taktzeit bei gleichbleibender Wiederholgenauigkeit. Dazu wird ein "
        "datengetriebenes Verfahren mit klassischer Regelung verglichen.\n\n"
        "## 2 Grundlagen\n\n"
        "Ein Industrieroboter besteht aus mehreren rotatorischen Achsen. "
        "Die Kinematik beschreibt den Zusammenhang zwischen Gelenkwinkeln "
        "und Endeffektorpose. Prof. Berger beschreibt dies u.a. im "
        "Vorlesungsskript. " + long_body + "\n\n"
        "## 3 Methodik\n\n"
        "Zur Bewertung wurde die Wiederholgenauigkeit nach ISO 9283 "
        "gemessen. Die Ergebnisse sind in der folgenden Tabelle "
        "zusammengefasst.\n\n"
        "## Literaturverzeichnis\n\n"
        "[1] Berger, K.: Automatisierungstechnik. BTU Cottbus, 2024.\n"
        "[2] ISO 9283: Industrieroboter — Leistungskenngroessen.\n\n"
        "## Eidesstattliche Erklaerung\n\n"
        "Hiermit versichere ich, dass ich die vorliegende Arbeit "
        "selbststaendig verfasst habe.\n"
    )
    return ExtractedDoc(
        source="/data/manual/abschlussarbeiten/masterarbeit_bahnplanung.pdf",
        source_type="pdf",
        title="Optimierung der Bahnplanung eines Industrieroboters",
        body_md=body,
        tables=[_oversized_table()],
    )


def _chunk_and_filter(
    doc: ExtractedDoc, doc_type: str,
) -> tuple[list[Chunk], list[Chunk]]:
    """Chunkt ein Dokument und filtert es; liefert (raw, gefiltert)."""
    chunker = MarkdownChunker()
    raw = chunker.chunk(doc, doc_type=doc_type)
    kept = filter_chunks(raw, doc_type=doc_type)
    return raw, kept


# ── Harte Invarianten ──


class TestChunkQualityInvariants:
    """Harte Garantien, die jeder Chunk-Satz erfuellen muss."""

    def test_no_chunk_over_max_tokens(self) -> None:
        """Kein Chunk ueberschreitet chunk_max_tokens (harte Grenze)."""
        s = get_settings()
        raw, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        for chunk in raw + kept:
            tokens = count_tokens(chunk.text)
            assert tokens <= s.chunk_max_tokens, (
                f"Chunk {chunk.chunk_index} hat {tokens} Tokens "
                f"(max {s.chunk_max_tokens})"
            )

    def test_no_empty_chunks(self) -> None:
        """Kein Chunk ist leer oder nur Whitespace."""
        _, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        assert kept
        for chunk in kept:
            assert chunk.text.strip(), f"Chunk {chunk.chunk_index} ist leer"

    def test_offsets_within_body_and_ordered(self) -> None:
        """Body-Chunk-Offsets liegen im Body und sind geordnet."""
        doc = build_abschlussarbeit()
        raw, _ = _chunk_and_filter(doc, "abschlussarbeit")
        n = len(doc.body_md)
        for chunk in raw:
            if chunk.is_table:
                continue
            assert 0 <= chunk.char_start <= chunk.char_end <= n, (
                f"Ungueltige Offsets: {chunk.char_start}..{chunk.char_end} "
                f"(Body {n})"
            )

    def test_indices_continuous(self) -> None:
        """chunk_index ist nach dem Filtern fortlaufend ab 0."""
        _, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        assert [c.chunk_index for c in kept] == list(range(len(kept)))

    def test_split_table_keeps_header_everywhere(self) -> None:
        """Jeder Teil einer geteilten Tabelle traegt Header + Separator.

        Chunker-Invariante — auf der Rohausgabe geprueft (der Filter ist
        eine separate Stufe, siehe TestTailMatterTableRegression).
        """
        raw, _ = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        table_chunks = [c for c in raw if c.is_table]
        assert len(table_chunks) > 1, "Uebergrosse Tabelle wurde nicht geteilt"
        for tc in table_chunks:
            assert "Messpunkt" in tc.text, "Header fehlt in Tabellen-Teil"
            assert "---" in tc.text, "Separator fehlt in Tabellen-Teil"


# ── Filter-Verhalten (Front-/Tail-Matter) ──


class TestFilterBehaviour:
    """Front- und Tail-Matter muessen fuer Abschlussarbeiten fallen."""

    def test_front_and_tail_matter_dropped(self) -> None:
        """Inhaltsverzeichnis, Literatur und Erklaerung sind weg."""
        _, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        joined = "\n".join(c.text for c in kept)
        assert "Inhaltsverzeichnis" not in joined
        assert "selbststaendig verfasst" not in joined
        assert "Berger, K.: Automatisierungstechnik" not in joined

    def test_body_content_survives(self) -> None:
        """Fachinhalt (Kapitel) bleibt erhalten."""
        _, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        joined = "\n".join(c.text for c in kept)
        assert "Wiederholgenauigkeit" in joined
        assert "Endeffektorpose" in joined


class TestTailMatterTableRegression:
    """Dokumentierter Qualitaets-Defekt: Tabellen fallen unter Tail-Matter.

    Der Chunker haengt Tabellen-Chunks ans Listenende — also positional
    HINTER den Tail-Matter-Cutoff (Literaturverzeichnis/Anhang). Der
    positionale Tail-Matter-Filter verwirft dadurch bei Abschlussarbeiten
    und Promotionen ALLE Tabellen, auch inhaltstragende Ergebnistabellen.

    Belegt durch scripts/eval_chunk_quality.py (NACH Filter: Tabelle 0).
    Der Test ist ``strict=True`` xfail: sobald der Defekt behoben ist,
    schlaegt er als XPASS an und muss angepasst werden.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="BUG: Tabellen werden ans Listenende gehaengt und fallen "
        "positional hinter den Tail-Matter-Cutoff — Ergebnistabellen gehen "
        "fuer Abschlussarbeiten/Promotionen verloren.",
    )
    def test_content_tables_survive_tail_matter(self) -> None:
        """Soll-Verhalten: inhaltstragende Tabellen ueberleben den Filter."""
        _, kept = _chunk_and_filter(build_abschlussarbeit(), "abschlussarbeit")
        table_chunks = [c for c in kept if c.is_table]
        assert table_chunks, (
            "Alle Tabellen-Chunks wurden vom Tail-Matter-Filter verworfen"
        )


# ── Aggregierte Qualitaetsbaender (die eigentliche Evaluation) ──


class TestChunkQualityBands:
    """Aggregatkennzahlen muessen im gesunden Band liegen."""

    def test_quality_report_bands(self) -> None:
        """evaluate_chunks liefert Kennzahlen im erwarteten Rahmen."""
        s = get_settings()
        doc = build_abschlussarbeit()
        raw, kept = _chunk_and_filter(doc, "abschlussarbeit")
        thresholds = QualityThresholds(
            max_tokens=s.chunk_max_tokens,
            target_tokens=s.chunk_target_tokens,
        )
        report = evaluate_chunks(kept, doc.body_md, thresholds)

        # Harte Garantien
        assert report.oversize_count == 0
        assert report.empty_chunks == 0
        # Gesunde Groesse dominiert (kurze Kapitel-Intros bleiben Fragmente)
        assert report.healthy_fraction >= 0.7
        # Heading-Kontext fuer Retrieval vorhanden
        assert report.heading_coverage >= 0.8
        # Chunker verliert kaum Body-Zeichen (vor dem Filtern gemessen)
        raw_report = evaluate_chunks(raw, doc.body_md, thresholds)
        assert raw_report.char_coverage >= 0.9
        # Alle Tabellen-Teile behalten den Header (Chunker-Rohausgabe)
        assert raw_report.table_header_fraction == 1.0

    def test_mean_tokens_near_target(self) -> None:
        """Durchschnittliche Body-Chunk-Groesse liegt nicht winzig."""
        s = get_settings()
        doc = build_abschlussarbeit()
        _, kept = _chunk_and_filter(doc, "abschlussarbeit")
        report = evaluate_chunks(kept, doc.body_md)
        # Mittelwert soll spuerbar ueber der Fragment-Schwelle liegen
        assert report.token_mean >= 64
        assert report.token_max <= s.chunk_max_tokens
