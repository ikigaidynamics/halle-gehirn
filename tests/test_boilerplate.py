"""Tests for the boilerplate cleaning module."""


from halle_gehirn.extraction.boilerplate import (
    clean,
    normalize_whitespace,
    remove_page_numbers,
)


def test_clean_removes_page_numbers():
    """clean() should strip lines that look like page numbers."""
    text = (
        "Some real content here.\n"
        "- 3 -\n"
        "More real content.\n"
        "Seite 5/20\n"
        "Final paragraph.\n"
        "Page 12\n"
    )
    result = clean(text)
    assert "- 3 -" not in result
    assert "Seite 5/20" not in result
    assert "Page 12" not in result
    assert "Some real content here." in result
    assert "More real content." in result
    assert "Final paragraph." in result


def test_clean_removes_repeated_headers():
    """clean() should remove lines that appear 4+ times (threshold is 3+)."""
    header = "Stadtverwaltung Halle (Saale) - Vertraulich"
    paragraphs = [f"Paragraph {i} with unique content." for i in range(5)]
    lines = []
    for para in paragraphs:
        lines.append(header)
        lines.append(para)
    text = "\n".join(lines)

    result = clean(text)
    assert header not in result
    for para in paragraphs:
        assert para in result


def test_clean_preserves_content():
    """Normal paragraph text should pass through clean() essentially unchanged."""
    text = (
        "Dies ist ein ganz normaler Absatz ohne Seitenzahlen.\n"
        "\n"
        "Hier kommt ein zweiter Absatz mit Informationen.\n"
        "\n"
        "Und noch ein dritter Absatz zum Abschluss.\n"
    )
    result = clean(text)
    assert "Dies ist ein ganz normaler Absatz ohne Seitenzahlen." in result
    assert "Hier kommt ein zweiter Absatz mit Informationen." in result
    assert "Und noch ein dritter Absatz zum Abschluss." in result


def test_remove_page_numbers_patterns():
    """remove_page_numbers() should handle various page-number patterns."""
    # Pattern: "- 3 -"
    text = "Content before.\n- 3 -\nContent after."
    result = remove_page_numbers(text)
    assert "- 3 -" not in result
    assert "Content before." in result
    assert "Content after." in result

    # Pattern: "Seite 5"
    text = "Content before.\nSeite 5\nContent after."
    result = remove_page_numbers(text)
    assert "Seite 5" not in result
    assert "Content before." in result

    # Pattern: "Page 12"
    text = "Content before.\nPage 12\nContent after."
    result = remove_page_numbers(text)
    assert "Page 12" not in result
    assert "Content before." in result

    # Pattern: bare number on a line, e.g. "42"
    text = "Content before.\n42\nContent after."
    result = remove_page_numbers(text)
    assert "42" not in result.splitlines()
    assert "Content before." in result
    assert "Content after." in result


def test_normalize_whitespace_collapses():
    """4+ consecutive blank lines should be collapsed to at most 2."""
    text = "First paragraph.\n\n\n\n\nSecond paragraph."
    result = normalize_whitespace(text)

    # Count the maximum run of consecutive blank lines
    max_blank_run = 0
    current_run = 0
    for line in result.splitlines():
        if line.strip() == "":
            current_run += 1
            max_blank_run = max(max_blank_run, current_run)
        else:
            current_run = 0

    assert max_blank_run <= 2, (
        f"Expected at most 2 consecutive blank lines, found {max_blank_run}"
    )
    assert "First paragraph." in result
    assert "Second paragraph." in result
