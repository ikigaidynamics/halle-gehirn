"""Struktur- und token-bewusster Markdown-Chunker.

Zerlegt ExtractedDoc-Markdown in Chunks mit Zeichen-Offsets.
Heading-Split → Satz-Split → harter Zeilen/Wort-Split als Fallback.
Kein Chunk verlässt chunk() ueber CHUNK_MAX_TOKENS.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import structlog
import tiktoken

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.extraction.base import ExtractedDoc
from halle_gehirn.pipeline.chunk_helpers import (
    Section,
    hard_split_text,
    split_sections,
    split_table,
)
from halle_gehirn.pipeline.sentence_splitter import Sentence, split_sentences

logger = structlog.get_logger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")

# ── doc_type-Profile ──

@dataclass(frozen=True)
class ChunkProfile:
    """Doc-type-spezifisches Chunking-Verhalten."""

    filter_front_matter: bool = False
    prefer_tables_whole: bool = False
    simple_path: bool = False


PROFILES: dict[str, ChunkProfile] = {
    "abschlussarbeit": ChunkProfile(filter_front_matter=True),
    "promotion": ChunkProfile(filter_front_matter=True),
    "handbuch": ChunkProfile(prefer_tables_whole=True),
    "anlagendoku": ChunkProfile(prefer_tables_whole=True),
    "flyer": ChunkProfile(simple_path=True),
    "online_beitrag": ChunkProfile(simple_path=True),
}

DEFAULT_PROFILE = ChunkProfile()


# ── Chunk-Datentyp ──


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
    """Zaehlt Tokens mit tiktoken (cl100k_base)."""
    return len(_ENCODING.encode(text, disallowed_special=()))


class MarkdownChunker:
    """Struktur- und token-bewusster Chunker fuer Markdown."""

    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self._target = s.chunk_target_tokens
        self._max = s.chunk_max_tokens
        logger.info(
            "chunker_init",
            target_tokens=self._target,
            max_tokens=self._max,
        )

    def chunk(
        self, doc: ExtractedDoc, doc_type: str = "",
    ) -> list[Chunk]:
        """Zerlegt ein ExtractedDoc in token-begrenzte Chunks."""
        profile = PROFILES.get(doc_type, DEFAULT_PROFILE)
        body_tokens = count_tokens(doc.body_md)
        logger.info(
            "chunking_start",
            source=doc.source,
            body_chars=len(doc.body_md),
            body_tokens=body_tokens,
            tables=len(doc.tables),
            doc_type=doc_type or "(default)",
            profile=type(profile).__name__,
        )

        chunks: list[Chunk] = []

        # Body-Chunks: simple_path fuer kurze Dokumente
        if profile.simple_path and body_tokens <= self._max:
            body = doc.body_md.strip()
            if body:
                chunks.append(Chunk(
                    text=body,
                    char_start=0,
                    char_end=len(body),
                    chunk_index=0,
                ))
        else:
            chunks.extend(self._chunk_body(doc.body_md))

        # Tabellen als eigene Chunks (mit Token-Limit)
        for tbl in doc.tables:
            if not tbl.markdown.strip():
                continue
            table_parts = split_table(
                tbl.markdown.strip(), self._max, tbl.page, count_tokens,
            )
            for part in table_parts:
                chunks.append(Chunk(
                    text=part["text"],  # type: ignore[arg-type]
                    char_start=0,
                    char_end=len(part["text"]),  # type: ignore[arg-type]
                    chunk_index=0,
                    page=part["page"],  # type: ignore[arg-type]
                    is_table=True,
                ))

        # Harte Token-Grenze durchsetzen (letzter Ausweg)
        chunks = self._enforce_hard_limit(chunks)

        # chunk_index fortlaufend setzen
        for idx, c in enumerate(chunks):
            c.chunk_index = idx

        self._log_summary(doc.source, chunks)
        return chunks

    def _log_summary(self, source: str, chunks: list[Chunk]) -> None:
        """Loggt Zusammenfassung nach dem Chunking."""
        table_count = sum(1 for c in chunks if c.is_table)
        token_counts = [count_tokens(c.text) for c in chunks]
        logger.info(
            "chunking_done",
            source=source,
            body_chunks=len(chunks) - table_count,
            table_chunks=table_count,
            total_chunks=len(chunks),
            avg_tokens=(
                round(sum(token_counts) / len(token_counts))
                if token_counts else 0
            ),
            min_tokens=min(token_counts) if token_counts else 0,
            max_tokens=max(token_counts) if token_counts else 0,
        )

    def _chunk_body(self, body: str) -> list[Chunk]:
        """Zerlegt den Body-Markdown in Chunks."""
        sections = split_sections(body)
        logger.debug(
            "chunking_sections",
            section_count=len(sections),
            headings=[
                s.headings[0] if s.headings else "(kein Heading)"
                for s in sections
            ],
        )
        chunks: list[Chunk] = []
        for section in sections:
            section_chunks = self._chunk_section(section)
            chunks.extend(section_chunks)
        return chunks

    def _chunk_section(self, section: Section) -> list[Chunk]:
        """Zerlegt eine Section in token-begrenzte Chunks."""
        text = section.text.strip()
        if not text:
            return []
        tokens = count_tokens(text)
        heading = section.headings[0] if section.headings else "(kein Heading)"
        if tokens <= self._max:
            logger.debug(
                "section_single_chunk",
                heading=heading,
                tokens=tokens,
                strategy="single",
            )
            return [Chunk(
                text=text,
                char_start=section.start,
                char_end=section.start + len(text),
                chunk_index=0,
                headings=section.headings,
            )]
        # Zu gross — per Satz aufteilen
        logger.debug(
            "section_sentence_split",
            heading=heading,
            tokens=tokens,
            max_tokens=self._max,
            strategy="sentence_split",
        )
        return self._split_by_sentences(section)

    def _split_by_sentences(self, section: Section) -> list[Chunk]:
        """Teilt eine zu grosse Section an Satzgrenzen auf."""
        sentences = split_sentences(section.text)
        if not sentences:
            # Kein Satz erkannt — harter Fallback
            return self._hard_split_chunks(
                section.text.strip(), section.headings, section.start,
            )
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

    # ── Harter Fallback: Zeilen- / Wort-Split ──

    def _hard_split_chunks(
        self, text: str, headings: list[str], offset: int,
    ) -> list[Chunk]:
        """Teilt Text per hard_split_text() und baut Chunk-Objekte."""
        spans = hard_split_text(
            text, self._max, offset, count_tokens,
            lambda t: _ENCODING.encode(t, disallowed_special=()),
            _ENCODING.decode,
        )
        return [
            Chunk(
                text=s.text, char_start=s.start, char_end=s.end,
                chunk_index=0, headings=headings,
            )
            for s in spans
        ]

    def _enforce_hard_limit(self, chunks: list[Chunk]) -> list[Chunk]:
        """Garantiert: kein Chunk ueber self._max Token."""
        result: list[Chunk] = []
        for chunk in chunks:
            tokens = count_tokens(chunk.text)
            if tokens <= self._max:
                result.append(chunk)
                continue
            heading = (
                chunk.headings[0] if chunk.headings else "(kein Heading)"
            )
            logger.warning(
                "chunk_hard_split",
                heading=heading,
                original_tokens=tokens,
                max_tokens=self._max,
            )
            sub_chunks = self._hard_split_chunks(
                chunk.text, chunk.headings, chunk.char_start,
            )
            for sc in sub_chunks:
                sc.page = chunk.page
                sc.is_table = chunk.is_table
            result.extend(sub_chunks)
        return result
