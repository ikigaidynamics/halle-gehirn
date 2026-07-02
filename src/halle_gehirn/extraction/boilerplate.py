"""Boilerplate and noise removal for extracted text.

This module cleans raw extracted text by stripping navigation elements,
repeated headers and footers, page numbers, and other boilerplate content
commonly found in PDF and HTML documents.
"""

from __future__ import annotations

import re
from collections import Counter

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

# Lines that consist solely of a page number (with optional surrounding noise).
_PAGE_NUMBER_RE = re.compile(
    r"""^                      # start of line
    [\s\-\u2014]*              # optional leading whitespace / dashes
    (?:                        # page-number variants
        (?:page|seite|s\.)     # keyword prefix
        [\s.:]*
    )?
    \d{1,5}                    # the actual number
    (?:                        # optional " of N" suffix
        \s*/\s*\d{1,5}
        | \s+(?:of|von)\s+\d{1,5}
    )?
    [\s\-\u2014]*$             # trailing whitespace / dashes
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)

# Common navigation / chrome patterns (one per line).
_NAV_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"^\s*(?:home|zur\u00fcck|back|next|weiter|previous|inhalt"
        r"|table\s+of\s+contents)\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:click here|hier klicken|skip to|springe zu).*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:copyright|\u00a9|\(c\))\s.*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:all rights reserved|alle rechte vorbehalten).*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*(?:impressum|datenschutz|privacy policy|cookie).*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"^\s*\|\s*(?:home|contact|kontakt|about|\u00fcber uns).*$",
        re.IGNORECASE | re.MULTILINE,
    ),
]

# Separator lines: lines made only of dashes, underscores, equals, or asterisks.
_SEPARATOR_LINE_RE = re.compile(
    r"^\s*[-=_*]{4,}\s*$",
    re.MULTILINE,
)

# Excessive blank lines (three or more in a row).
_EXCESS_BLANK_RE = re.compile(r"\n{3,}")

# Leading/trailing whitespace on each line.
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clean(text: str) -> str:
    """Remove boilerplate and noise from extracted text.

    Applies all cleaning steps in sequence: page-number removal,
    navigation stripping, repeated-header removal, and whitespace
    normalisation.

    Args:
        text: Raw extracted text.

    Returns:
        Cleaned text with boilerplate removed.
    """
    if not text:
        return text

    original_len = len(text)

    text = remove_page_numbers(text)
    text = _remove_nav_chrome(text)
    text = remove_repeated_headers(text)
    text = _remove_separator_lines(text)
    text = normalize_whitespace(text)

    removed = original_len - len(text)
    if removed > 0:
        logger.debug(
            "boilerplate.cleaned",
            original_len=original_len,
            cleaned_len=len(text),
            removed_chars=removed,
        )

    return text


def remove_page_numbers(text: str) -> str:
    """Strip lines that contain only page numbers.

    Recognises patterns such as ``- 3 -``, ``Page 12``, ``Seite 5/20``,
    and bare numbers standing alone on a line.

    Args:
        text: Input text.

    Returns:
        Text with page-number-only lines removed.
    """
    return _PAGE_NUMBER_RE.sub("", text)


def remove_repeated_headers(text: str, *, min_repeats: int = 3) -> str:
    """Remove lines that appear verbatim more than *min_repeats* times.

    Documents produced by PDF extraction often repeat the same header or
    footer on every page.  This function detects such lines and strips
    all occurrences.

    Args:
        text: Input text.
        min_repeats: A line must appear at least this many times to be
            considered a repeated header/footer.  Defaults to ``3``.

    Returns:
        Text with repeated header/footer lines removed.
    """
    lines = text.split("\n")
    normalised = [line.strip() for line in lines]

    # Count non-empty normalised lines.
    counts: Counter[str] = Counter(
        line for line in normalised if line
    )

    repeated = {
        line for line, count in counts.items() if count >= min_repeats
    }

    if not repeated:
        return text

    logger.debug(
        "boilerplate.repeated_headers",
        patterns=[r[:60] for r in list(repeated)[:5]],
    )

    result_lines = [
        line
        for line, norm in zip(lines, normalised, strict=True)
        if norm not in repeated
    ]

    return "\n".join(result_lines)


def normalize_whitespace(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks.

    Specifically this function:

    * Strips trailing whitespace from every line.
    * Collapses runs of three or more blank lines into two (one blank
      line between paragraphs).
    * Strips leading and trailing whitespace from the whole document.

    Args:
        text: Input text.

    Returns:
        Text with normalised whitespace.
    """
    text = _TRAILING_WS_RE.sub("", text)
    text = _EXCESS_BLANK_RE.sub("\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _remove_nav_chrome(text: str) -> str:
    """Remove navigation and website-chrome lines.

    Args:
        text: Input text.

    Returns:
        Text with navigation boilerplate lines removed.
    """
    for pattern in _NAV_PATTERNS:
        text = pattern.sub("", text)
    return text


def _remove_separator_lines(text: str) -> str:
    """Remove lines consisting only of separator characters.

    Args:
        text: Input text.

    Returns:
        Text with separator lines removed.
    """
    return _SEPARATOR_LINE_RE.sub("", text)
