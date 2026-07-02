"""Title extraction module for the Halle-Gehirn RAG system.

Extracts document titles using heuristics when metadata does not
provide one.  The extraction pipeline tries, in order:

1. Markdown H1 heading (``# Title``)
2. First non-empty, non-whitespace line (if shorter than 200 characters)
3. Filename stem derived from the *source* path

All returned titles are stripped of leading/trailing whitespace and
any residual markdown formatting characters.
"""

from __future__ import annotations

import pathlib
import re

import structlog

__all__ = ["extract_title"]

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_H1_PATTERN: re.Pattern[str] = re.compile(r"^#\s+(.+)$", re.MULTILINE)
"""Regex matching a Markdown H1 heading (e.g. ``# My Title``)."""

_MAX_FIRST_LINE_LENGTH: int = 200
"""Maximum length of the first non-empty line to be considered a title."""

_STRIP_CHARS: str = "# \t"
"""Characters to strip from the extracted raw title string."""


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _clean_title(raw: str) -> str:
    """Clean a raw title string.

    Removes leading/trailing whitespace, markdown heading markers,
    and other formatting artifacts.

    Args:
        raw: The raw title string to clean.

    Returns:
        A cleaned title string.
    """
    cleaned = raw.strip(_STRIP_CHARS)
    # Collapse any internal runs of whitespace to a single space.
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_from_heading(body_md: str) -> str | None:
    """Try to extract a title from the first Markdown H1 heading.

    Args:
        body_md: The full markdown body of the document.

    Returns:
        The cleaned heading text, or ``None`` if no H1 heading is found.
    """
    match = _H1_PATTERN.search(body_md)
    if match is None:
        return None

    raw = match.group(1)
    title = _clean_title(raw)
    if not title:
        return None

    log.debug("title_extracted_from_heading", title=title)
    return title


def _extract_from_first_line(body_md: str) -> str | None:
    """Try to extract a title from the first non-empty line.

    The line is only accepted when it is shorter than
    ``_MAX_FIRST_LINE_LENGTH`` characters, which avoids treating a long
    opening paragraph as a title.

    Args:
        body_md: The full markdown body of the document.

    Returns:
        The cleaned first line, or ``None`` if no suitable line is found.
    """
    for line in body_md.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        cleaned = _clean_title(stripped)
        if not cleaned:
            continue

        if len(cleaned) >= _MAX_FIRST_LINE_LENGTH:
            log.debug(
                "first_line_too_long",
                length=len(cleaned),
                max_length=_MAX_FIRST_LINE_LENGTH,
            )
            return None

        log.debug("title_extracted_from_first_line", title=cleaned)
        return cleaned

    return None


def _extract_from_filename(source: str) -> str:
    """Derive a fallback title from the filename stem.

    Args:
        source: A file path or URI string identifying the document source.

    Returns:
        The filename stem (without extension) as the fallback title.
    """
    stem = pathlib.PurePosixPath(source).stem
    if not stem or stem == ".":
        # Second attempt with a Windows-style path.
        stem = pathlib.PureWindowsPath(source).stem

    # Replace common separators with spaces for readability.
    title = stem.replace("_", " ").replace("-", " ").strip()

    if not title:
        title = "Untitled"

    log.debug("title_extracted_from_filename", title=title, source=source)
    return title


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_title(body_md: str, source: str) -> str:
    """Extract a document title using a cascade of heuristics.

    The function attempts to determine a human-readable title for a
    document by trying the following strategies in order:

    1. **Markdown H1 heading** -- looks for the first ``# Heading``
       line in *body_md*.
    2. **First non-empty line** -- uses the first non-blank line if it
       is shorter than 200 characters.
    3. **Filename stem** -- derives a title from the *source* path by
       taking the filename without its extension.

    Args:
        body_md: The markdown body of the document.  May be empty.
        source: A file path or URI identifying where the document
            originated (used as a last-resort fallback).

    Returns:
        A non-empty title string.  The value is always stripped of
        leading/trailing whitespace.
    """
    log.debug(
        "extract_title_called",
        source=source,
        body_length=len(body_md) if body_md else 0,
    )

    if body_md:
        # Strategy 1: Markdown H1 heading.
        title = _extract_from_heading(body_md)
        if title:
            return title

        # Strategy 2: First non-empty line.
        title = _extract_from_first_line(body_md)
        if title:
            return title

    # Strategy 3: Filename stem.
    return _extract_from_filename(source)
