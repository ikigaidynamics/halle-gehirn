"""Tests fuer den Extraktions-Artefakt-Sanitizer.

Testet alle 5 Regeln mit echten Beispielen aus dem Schwier-Chunk
sowie Negativtests fuer falsch-positive Schutzlogik.
"""

from halle_gehirn.extraction.text_sanitizer import SanitizerStats, sanitize


# ===================================================================
# Regel 1: ÿ → ß  (kontextgeprueft)
# ===================================================================


class TestEszettFix:
    """ÿ innerhalb von Kleinbuchstaben → ß."""

    def test_fliessbandfertigung(self):
        text = "innerhalb einer Flieÿbandfertigung"
        result, stats = sanitize(text)
        assert result == "innerhalb einer Fließbandfertigung"
        assert stats.ypsilon_to_eszett == 1

    def test_grossen(self):
        text = "Voraussetzungen für groÿe Bauteile"
        result, stats = sanitize(text)
        assert result == "Voraussetzungen für große Bauteile"
        assert stats.ypsilon_to_eszett == 1

    def test_multiple_in_text(self):
        text = "Flieÿband und Schweißen bei groÿen Maÿen"
        # Note: Schweißen already has real ß, Maÿen has ÿ
        result, stats = sanitize(text)
        assert "Fließband" in result
        assert "großen" in result
        assert "Maßen" in result
        assert stats.ypsilon_to_eszett == 3

    def test_negative_french_name_preserved(self):
        """Franzoesischer Eigenname mit ÿ bleibt unveraendert."""
        text = "Paul Ÿves war ein bekannter Forscher"
        result, _ = sanitize(text)
        # Ÿ steht nach Leerzeichen, nicht nach Kleinbuchstabe → kein Match
        assert "Ÿves" in result

    def test_negative_isolated_ypsilon(self):
        """Einzelnes ÿ ohne Kleinbuchstaben-Kontext bleibt."""
        text = "Der Wert ÿ ist definiert"
        result, stats = sanitize(text)
        assert "ÿ" in result
        assert stats.ypsilon_to_eszett == 0

    def test_negative_uppercase_before(self):
        """ÿ nach Grossbuchstabe → kein Ersatz."""
        text = "ABCÿDEF"
        result, stats = sanitize(text)
        assert "ÿ" in result
        assert stats.ypsilon_to_eszett == 0


# ===================================================================
# Regel 2: Steuerzeichen / Ligatur-Codepoints → aufgeloeste Ligaturen
# ===================================================================


class TestLigatureFix:
    """Steuerzeichen und Unicode-Ligaturen → Buchstaben."""

    def test_esc_to_ff(self):
        """U+001B (ESC) → 'ff' — haeufigster Fall."""
        text = "Sto\x1beigenschaften"
        result, stats = sanitize(text)
        assert result == "Stoffeigenschaften"
        assert stats.ligature_restored == 1

    def test_unicode_fi_ligature(self):
        text = "De\ufb01nition"
        result, stats = sanitize(text)
        assert result == "Definition"
        assert stats.ligature_restored == 1

    def test_unicode_fl_ligature(self):
        text = "Ein\ufb02uss"
        result, stats = sanitize(text)
        assert result == "Einfluss"
        assert stats.ligature_restored == 1

    def test_unicode_ffi_ligature(self):
        # \ufb03 = ffi-Ligatur; "Koe" + Ligatur + "zient" → "Koeffizient"
        text = "Koe\ufb03zient"
        result, stats = sanitize(text)
        assert result == "Koeffizient"
        assert stats.ligature_restored == 1

    def test_unicode_ff_ligature(self):
        text = "Sto\ufb00eigenschaften"
        result, stats = sanitize(text)
        assert result == "Stoffeigenschaften"
        assert stats.ligature_restored == 1

    def test_multiple_ligatures(self):
        text = "Sto\x1beigenschaften \u00e4ndern — De\ufb01nition"
        result, stats = sanitize(text)
        assert "Stoffeigenschaften" in result
        assert "Definition" in result
        assert stats.ligature_restored == 2

    def test_logging_details(self):
        text = "Sto\x1beigen und De\ufb01nition"
        _, stats = sanitize(text)
        assert stats.ligature_details["ff"] == 1
        assert stats.ligature_details["fi"] == 1


# ===================================================================
# Regel 3: LaTeX-Diakritika rekombinieren
# ===================================================================


class TestDiacriticFix:
    """Getrennte ¨ + Vokal → Umlaut."""

    def test_umlaut_u(self):
        text = "F\u00a8ugen"
        result, stats = sanitize(text)
        assert result == "Fügen"
        assert stats.diacritic_combined == 1

    def test_umlaut_a(self):
        text = "\u00a8andern"
        result, stats = sanitize(text)
        assert result == "ändern"
        assert stats.diacritic_combined == 1

    def test_umlaut_o(self):
        text = "geh\u00a8ort"
        result, stats = sanitize(text)
        assert result == "gehört"
        assert stats.diacritic_combined == 1

    def test_uppercase_umlaut(self):
        text = "\u00a8Ubersicht"
        result, stats = sanitize(text)
        assert result == "Übersicht"
        assert stats.diacritic_combined == 1

    def test_diaeresis_with_space(self):
        """¨ + Leerzeichen + Vokal (manchmal mit Whitespace getrennt)."""
        text = "F\u00a8 ugen"
        result, stats = sanitize(text)
        assert result == "Fügen"
        assert stats.diacritic_combined == 1

    def test_latex_backslash_quote(self):
        r"""LaTeX-Rohform \"a → ä."""
        text = 'Stof-\neigenschaften-\n\\"andern'
        result, stats = sanitize(text)
        assert "ändern" in result

    def test_multiple_diacritics(self):
        text = "F\u00a8ugen und \u00a8Andern, d.h. \u00a8ublich"
        result, stats = sanitize(text)
        assert "Fügen" in result
        assert "Ändern" in result
        assert "üblich" in result
        assert stats.diacritic_combined == 3


# ===================================================================
# Regel 4: Silbentrennung zusammenfuehren
# ===================================================================


class TestHyphenationFix:
    """Silbentrennung ueber Zeilenumbruch → zusammenziehen."""

    def test_basic_hyphenation(self):
        # Silbentrennung: "Stof" + "-\n" + "eigenschaften" → "Stofeigenschaften"
        # Das zweite 'f' war im OCR bereits verloren — Sanitizer kann es
        # nicht rekonstruieren, das ist korrektes Verhalten.
        text = "Stof-\neigenschaften"
        result, stats = sanitize(text)
        assert result == "Stofeigenschaften"
        assert stats.hyphenation_joined == 1

    def test_hyphenation_with_indent(self):
        text = "Applika-\n  tionstechnik"
        result, stats = sanitize(text)
        assert result == "Applikationstechnik"
        assert stats.hyphenation_joined == 1

    def test_negative_real_compound(self):
        """Echtes Kompositum mit Bindestrich + Grossbuchstabe bleibt."""
        text = "Fahrzeug-\nReparaturbranche"
        result, stats = sanitize(text)
        # 'R' ist Grossbuchstabe → kein Join
        assert "Fahrzeug-\nReparaturbranche" in result
        assert stats.hyphenation_joined == 0

    def test_negative_line_break_without_hyphen(self):
        """Normaler Zeilenumbruch ohne Bindestrich → kein Join."""
        text = "Ende des Satzes.\nNeuer Satz beginnt."
        result, stats = sanitize(text)
        assert "Ende des Satzes.\nNeuer Satz beginnt." in result
        assert stats.hyphenation_joined == 0

    def test_soft_hyphen(self):
        """Soft Hyphen (U+00AD) wird auch behandelt."""
        text = "Applika\u00ad\ntionstechnik"
        result, stats = sanitize(text)
        assert result == "Applikationstechnik"
        assert stats.hyphenation_joined == 1

    def test_negative_standalone_hyphen(self):
        """Bindestrich-Aufzaehlung bleibt."""
        text = "Punkte:\n- erster Punkt\n- zweiter Punkt"
        result, stats = sanitize(text)
        assert "- erster Punkt" in result
        assert stats.hyphenation_joined == 0


# ===================================================================
# Regel 5: <br>-Tags → Leerzeichen
# ===================================================================


class TestBrTagFix:
    """<br>-Tags in Tabellenzellen → Leerzeichen."""

    def test_br_basic(self):
        text = "|1)<br>Urformen|2)<br>Umformen|"
        result, stats = sanitize(text)
        assert result == "|1) Urformen|2) Umformen|"
        assert stats.br_tags_removed == 2

    def test_br_self_closing(self):
        text = "Text<br/>mehr Text<br />Ende"
        result, stats = sanitize(text)
        assert result == "Text mehr Text Ende"
        assert stats.br_tags_removed == 2

    def test_br_case_insensitive(self):
        text = "Zeile<BR>Zeile<Br>Zeile"
        result, stats = sanitize(text)
        assert result == "Zeile Zeile Zeile"
        assert stats.br_tags_removed == 2

    def test_din8580_table_chunk(self):
        """Echter Tabellen-Chunk aus der Schwier-Arbeit."""
        text = (
            "|1)<br>Urformen|2)<br>Umformen|Fertigungs<br>(DIN <br>"
            "3)<br>Trennen|verfahren<br> 8580)<br>4)<br>F\u00a8ugen|"
            "5)<br>Beschichten|6)<br>Stof-<br>eigenschaften-<br>"
            "\u00a8andern|"
        )
        result, stats = sanitize(text)
        assert "<br" not in result
        assert "Fügen" in result
        assert "ändern" in result
        assert stats.br_tags_removed > 0
        assert stats.diacritic_combined >= 2


# ===================================================================
# Regel 6: Silbenumbrueche ohne Trennstrich in Tabellenzellen
# ===================================================================


class TestTableSyllableJoin:
    """Silbenumbrueche ohne Trennstrich in Tabellenzeilen reparieren."""

    # ── Regel 6a: kurze Fragmente (1-3 Buchstaben) ──

    def test_betriebstechnologie(self):
        text = "| Betriebstechnologi e | Kategorie |"
        result, stats = sanitize(text)
        assert "Betriebstechnologie" in result
        assert stats.table_syllable_joined == 1

    def test_anomalieerkennung(self):
        text = "| Anomalieerkennun g | Beschreibung |"
        result, stats = sanitize(text)
        assert "Anomalieerkennung" in result
        assert stats.table_syllable_joined == 1

    def test_benutzerfreundliche(self):
        text = "| benutzerfreundlich e Oberflaeche |"
        result, stats = sanitize(text)
        assert "benutzerfreundliche" in result
        assert stats.table_syllable_joined == 1

    def test_multiple_in_row(self):
        """Mehrere Fixes in einer Tabellenzeile."""
        text = "| Betriebstechnologi e | Anomalieerkennun g |"
        result, stats = sanitize(text)
        assert "Betriebstechnologie" in result
        assert "Anomalieerkennung" in result
        assert stats.table_syllable_joined == 2

    def test_negative_und_die(self):
        """'und die' darf NICHT zu 'unddie' werden."""
        text = "| und die Ergebnisse |"
        result, stats = sanitize(text)
        assert "und die" in result
        assert stats.table_syllable_joined == 0

    def test_negative_berichts_und(self):
        """'Berichts- und' bleibt unveraendert."""
        text = "| Berichts- und Benachrichtigungsfunktionen |"
        result, stats = sanitize(text)
        assert "Berichts- und" in result

    def test_only_table_lines(self):
        """Nicht-Tabellenzeilen bleiben unberuehrt."""
        text = "Betriebstechnologi e ist wichtig"
        result, stats = sanitize(text)
        assert "Betriebstechnologi e" in result
        assert stats.table_syllable_joined == 0

    # ── Regel 6b: lange Fragmente (Corpus-Kreuzreferenz) ──

    def test_informationstechnologie_with_corpus(self):
        """Langes Fragment wird gefixt wenn Wort im Corpus vorkommt."""
        text = "| Informationstechno logie | Beschreibung |"
        corpus = "Die Informationstechnologie spielt eine zentrale Rolle."
        result, stats = sanitize(text, corpus=corpus)
        assert "Informationstechnologie" in result
        assert stats.table_syllable_joined == 1

    def test_informationstechnologie_without_corpus(self):
        """Langes Fragment bleibt wenn Wort NICHT im Corpus vorkommt."""
        text = "| Informationstechno logie | Beschreibung |"
        result, stats = sanitize(text, corpus="Kein relevanter Text hier.")
        assert "Informationstechno logie" in result
        assert stats.table_syllable_uncertain > 0

    def test_benachrichtigungsfunktionen_with_corpus(self):
        """Langes Fragment vor langem Rest — Corpus-Match."""
        text = "| Benachrichtigungsf unktionen |"
        corpus = "Benachrichtigungsfunktionen und Dashboards"
        result, stats = sanitize(text, corpus=corpus)
        assert "Benachrichtigungsfunktionen" in result
        assert stats.table_syllable_joined == 1

    # ── Inline-Tabelle im Body (pymupdf4llm-Fall) ──

    def test_inline_table_in_body_self_corpus(self):
        """Body-Text mit Inline-Tabelle: Selbstreferenz-Corpus."""
        text = (
            "Die Informationstechnologie hat sich entwickelt.\n"
            "\n"
            "| Anbieter | Informationstechno logie |\n"
            "|---|---|\n"
            "| SAP | Betriebstechnologi e |\n"
        )
        # Selbstreferenz: der Fliesstext enthaelt "Informationstechnologie"
        result, stats = sanitize(text, corpus=text)
        assert "| Informationstechnologie |" in result
        # "Betriebstechnologi e" → 1-Buchstaben-Fragment → Regel 6a greift
        assert "Betriebstechnologie" in result
        assert stats.table_syllable_joined == 2

    # ── Sonstiges ──

    def test_stats_counted(self):
        """Stats werden korrekt gezaehlt."""
        text = "| Anomalieerkennun g | benutzerfreundlich e |"
        _, stats = sanitize(text)
        assert stats.table_syllable_joined == 2
        d = stats.as_dict()
        assert d["table_syllable_joined"] == 2

    def test_clean_table_unchanged(self):
        """Saubere Tabelle bleibt unveraendert."""
        text = "| Anbieter | Beschreibung | Preis |\n|---|---|---|"
        result, stats = sanitize(text)
        assert result == text
        assert stats.table_syllable_joined == 0


# ===================================================================
# Kombinierte Tests: Ganzer Chunk
# ===================================================================


class TestFullChunk:
    """Kompletter Chunk aus der Schwier-Arbeit."""

    def test_real_chunk_combined(self):
        """Realer Chunk mit mehreren Artefakt-Typen gleichzeitig."""
        text = (
            "In der Einteilung der Fertigungsverfahren nach DIN 8580 "
            "wird zwischen Urformen, Umformen, Trennen, F\u00a8ugen, "
            "Sto\x1beigenschaften \u00a8andern und Beschichten "
            "unterschieden. Letzteres ist in der Hauptgruppe 5 "
            "gef\u00a8uhrt und in einer Flieÿbandfertigung "
            "\u00a8ubersichtlich dargestellt."
        )
        result, stats = sanitize(text, source="Schwier_test")
        assert "Fügen" in result
        assert "Stoffeigenschaften" in result
        assert "ändern" in result
        assert "geführt" in result  # ¨u → ü
        assert "Fließbandfertigung" in result
        assert "übersichtlich" in result
        assert stats.total > 0

        # Keine Artefakte mehr
        assert "\x1b" not in result
        assert "\u00a8" not in result
        assert "ÿ" not in result

    def test_empty_input(self):
        result, stats = sanitize("")
        assert result == ""
        assert stats.total == 0

    def test_clean_input_unchanged(self):
        """Sauberer Text bleibt unveraendert."""
        text = "Dies ist ein sauberer deutscher Text mit Umlauten äöü."
        result, stats = sanitize(text)
        assert result == text
        assert stats.total == 0


# ===================================================================
# Stats
# ===================================================================


class TestStats:
    """SanitizerStats Datenstruktur."""

    def test_as_dict(self):
        _, stats = sanitize("Flieÿband-\nfertigung mit Sto\x1beigenschaften")
        d = stats.as_dict()
        assert "total" in d
        assert d["total"] > 0
        assert isinstance(d["total"], int)

    def test_total_sums_all_rules(self):
        stats = SanitizerStats(
            ypsilon_to_eszett=2,
            ligature_restored=3,
            diacritic_combined=1,
            hyphenation_joined=4,
            br_tags_removed=5,
            table_syllable_joined=6,
        )
        assert stats.total == 21

    def test_uncertain_not_in_total(self):
        """table_syllable_uncertain zaehlt NICHT zum total."""
        stats = SanitizerStats(table_syllable_uncertain=3)
        assert stats.total == 0
