"""Struktur- und token-bewusster Markdown-Chunker.

Zerlegt ExtractedDoc-Markdown in Chunks mit Zeichen-Offsets. Verwendet
den deutschen Satz-Splitter fuer saubere Grenzen und tiktoken fuer
Token-Zaehlung. Tabellen werden als eigene Chunks behandelt.

Orientiert sich am Docling-HybridChunker-Ansatz (Struktur + Token),
arbeitet aber auf Markdown — so kompatibel mit allen Extractoren.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import tiktoken

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.pipeline.sentence_splitter import Sentence, split_sentences

# Heading-Pattern: ## Heading oder ### Heading etc.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

# Tiktoken-Encoding fuer Token-Zaehlung
_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    """Ein Chunk mit Text, Offsets und Metadaten."""

    text: str
    char_start: int
    char_end: int
    chunk_index: int
    page: int | None = None
    headings: list[str] = field(default_factory=list)
    is_table: bool = False
    context_prefix: str | None = None


def count_tokens(text: str) -> int:
    """Zaehlt Tokens mit tiktoken (cl100k_base).

    Args:
        text: Zu zaehlender Text.

    Returns:
        Anzahl Tokens.
    """
    return len(_ENCODING.encode(text, disallowed_special=()))


class MarkdownChunker:
    """Struktur- und token-bewusster Chunker fuer Markdown.

    Zerlegt Markdown-Text in Chunks unter Beruecksichtigung von:
    - Heading-Hierarchie (##, ###, ...)
    - Absatzgrenzen
    - Satzgrenzen (deutscher Splitter)
    - Token-Limits (tiktoken)

    Tabellen aus ExtractedDoc werden als separate Chunks behandelt.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._target = s.chunk_target_tokens
        self._max = s.chunk_max_tokens

    def chunk(self, doc: ExtractedDoc) -> list[Chunk]:
        """Zerlegt ein ExtractedDoc in Chunks.

        Args:
            doc: Extrahiertes Dokument.

        Returns:
            Liste von Chunk-Objekten mit fortlaufendem chunk_index.
        """
        chunks: list[Chunk] = []
        # Body-Chunks
        body_chunks = self._chunk_body(doc.body_md)
        chunks.extend(body_chunks)
        # Tabellen als eigene Chunks
        for tbl in doc.tables:
            if not tbl.markdown.strip():
                continue
            chunks.append(Chunk(
                text=tbl.markdown.strip(),
                char_start=0,
                char_end=len(tbl.markdown.strip()),
                chunk_index=0,
                page=tbl.page,
                is_table=True,
            ))
        # chunk_index fortlaufend setzen
        for idx, c in enumerate(chunks):
            c.chunk_index = idx
        return chunks

    def _chunk_body(self, body: str) -> list[Chunk]:
        """Zerlegt den Body-Markdown in Chunks."""
        sections = _split_sections(body)
        chunks: list[Chunk] = []
        for section in sections:
            section_chunks = self._chunk_section(section)
            chunks.extend(section_chunks)
        return chunks

    def _chunk_section(self, section: _Section) -> list[Chunk]:
        """Zerlegt eine Section in token-begrenzte Chunks."""
        text = section.text.strip()
        if not text:
            return []
        tokens = count_tokens(text)
        if tokens <= self._max:
            return [Chunk(
                text=text,
                char_start=section.start,
                char_end=section.start + len(text),
                chunk_index=0,
                headings=section.headings,
            )]
        # Zu gross — per Satz aufteilen
        return self._split_by_sentences(section)

    def _split_by_sentences(self, section: _Section) -> list[Chunk]:
        """Teilt eine zu grosse Section an Satzgrenzen auf."""
        sentences = split_sentences(section.text)
        if not sentences:
            return [Chunk(
                text=section.text.strip(),
                char_start=section.start,
                char_end=section.start + len(section.text.strip()),
                chunk_index=0,
                headings=section.headings,
            )]
        chunks: list[Chunk] = []
        buffer: list[Sentence] = []
        buffer_tokens = 0

        for sent in sentences:
            sent_tokens = count_tokens(sent.text)
            if buffer and buffer_tokens + sent_tokens > self._target:
                chunks.append(self._flush_buffer(
                    buffer, section.start, section.headings,
                ))
                buffer = []
                buffer_tokens = 0
            buffer.append(sent)
            buffer_tokens += sent_tokens

        if buffer:
            chunks.append(self._flush_buffer(
                buffer, section.start, section.headings,
            ))
        return chunks

    def _flush_buffer(
        self,
        sentences: list[Sentence],
        section_offset: int,
        headings: list[str],
    ) -> Chunk:
        """Baut einen Chunk aus gesammelten Saetzen."""
        text = " ".join(s.text for s in sentences)
        first_start = section_offset + sentences[0].start
        last_end = section_offset + sentences[-1].end
        return Chunk(
            text=text,
            char_start=first_start,
            char_end=last_end,
            chunk_index=0,
            headings=headings,
        )


# ── Interne Hilfstypen ──


@dataclass
class _Section:
    """Ein Abschnitt im Markdown (Heading + zugehoeriger Text)."""

    text: str
    start: int
    headings: list[str] = field(default_factory=list)


def _split_sections(body: str) -> list[_Section]:
    """Teilt Markdown-Body an Headings in Sections auf."""
    if not body.strip():
        return []
    heading_matches = list(_HEADING_RE.finditer(body))
    if not heading_matches:
        return [_Section(text=body, start=0)]

    sections: list[_Section] = []
    # Text vor erstem Heading
    if heading_matches[0].start() > 0:
        pre = body[: heading_matches[0].start()]
        if pre.strip():
            sections.append(_Section(text=pre, start=0))

    for i, match in enumerate(heading_matches):
        heading_text = match.group(2).strip()
        start = match.start()
        end = (
            heading_matches[i + 1].start()
            if i + 1 < len(heading_matches)
            else len(body)
        )
        section_text = body[start:end]
        sections.append(_Section(
            text=section_text,
            start=start,
            headings=[heading_text],
        ))
    return sections
