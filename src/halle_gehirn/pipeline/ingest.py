"""Ingest-Pipeline: Extract -> Chunk -> Enrich -> Embed -> Payload.

Liest ``data/manifest.yaml``, validiert Slugs gegen ``data/vokabular.yaml``
(Fail-Fast bei unbekannten Slugs), extrahiert Dokumente, chunked, reichert
mit Kontext an, erzeugt Embeddings und baut ChunkPayloads.

Qdrant-Upsert erfolgt NICHT hier (Phase 3).
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog
import yaml

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.extraction.base import ExtractedDoc, ExtractionError, Extractor
from halle_gehirn.extraction.citation_index import parse_citations
from halle_gehirn.extraction.docling_extractor import DoclingExtractor
from halle_gehirn.extraction.glossar import parse_glossar
from halle_gehirn.extraction.plaintext_extractor import PlaintextExtractor
from halle_gehirn.extraction.text_sanitizer import sanitize as sanitize_text
from halle_gehirn.pipeline.chunk_filter import filter_chunks
from halle_gehirn.pipeline.chunker import Chunk, MarkdownChunker
from halle_gehirn.pipeline.context_enricher import OllamaContextEnricher
from halle_gehirn.pipeline.figure_linker import link_figures_to_chunks
from halle_gehirn.pipeline.progress import ProgressCallback, ProgressEvent
from halle_gehirn.pipeline.table_linker import link_tables_to_chunks
from halle_gehirn.vector_store.schema import (
    Bereich,
    ChunkPayload,
    DocType,
    Grad,
    Herkunft,
    Quelltyp,
    Status,
    Thema,
    Vertraulichkeit,
)

logger = structlog.get_logger(__name__)

_DATA_DIR = Path("data")
_MANIFEST_PATH = _DATA_DIR / "manifest.yaml"
_VOKABULAR_PATH = _DATA_DIR / "vokabular.yaml"
_MANUAL_DIR = _DATA_DIR / "manual"


class IngestError(Exception):
    """Fehler in der Ingest-Pipeline."""


class VokabularValidationError(IngestError):
    """Unbekannter Slug in manifest.yaml (nicht in vokabular.yaml)."""


class ChunkExplosionError(IngestError):
    """Dokument erzeugt absurd viele Chunks (Plausibilitaets-Abbruch)."""


@dataclass
class IngestStats:
    """Statistiken eines Ingest-Laufs."""

    docs_total: int = 0
    docs_success: int = 0
    docs_skipped: int = 0
    docs_unchanged: int = 0
    docs_failed: int = 0
    docs_filtered_empty: int = 0  # Extraktion ok, aber 0 Chunks nach Filter
    chunks_total: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ManifestEntry:
    """Ein Eintrag aus manifest.yaml (validiert)."""

    datei: str
    titel: str
    doc_type: str
    bereich: list[str]
    herkunft: str
    quelltyp: str = "primaer"
    thema: list[str] = field(default_factory=list)
    anlage: list[str] = field(default_factory=list)
    projekt: list[str] = field(default_factory=list)
    ansprechperson: list[str] = field(default_factory=list)
    autor: list[str] = field(default_factory=list)
    jahr: int | None = None
    vertraulichkeit: str = "intern"
    status: str = "final"
    grad: str | None = None
    do_ocr: bool | None = None


def load_manifest(path: Path | None = None) -> list[ManifestEntry]:
    """Laedt und parst manifest.yaml.

    Args:
        path: Optionaler Pfad (Default: data/manifest.yaml).

    Returns:
        Liste von ManifestEntry-Objekten.

    Raises:
        IngestError: Datei nicht gefunden oder ungueltig.
    """
    p = path or _MANIFEST_PATH
    if not p.exists():
        raise IngestError(f"Manifest nicht gefunden: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not raw or "dokumente" not in raw:
        raise IngestError(f"Manifest leer oder ohne 'dokumente'-Key: {p}")
    entries: list[ManifestEntry] = []
    for doc in raw["dokumente"]:
        entries.append(_parse_manifest_entry(doc))
    return entries


def _parse_manifest_entry(raw: dict[str, Any]) -> ManifestEntry:
    """Parst einen einzelnen Manifest-Eintrag."""
    bereich = raw.get("bereich", [])
    if isinstance(bereich, str):
        bereich = [bereich]
    thema = raw.get("thema", [])
    if isinstance(thema, str):
        thema = [thema]
    anlage = raw.get("anlage", [])
    if isinstance(anlage, str):
        anlage = [anlage]
    projekt = raw.get("projekt", [])
    if isinstance(projekt, str):
        projekt = [projekt]
    ansprechperson = raw.get("ansprechperson", [])
    if isinstance(ansprechperson, str):
        ansprechperson = [ansprechperson]
    autor = raw.get("autor", [])
    if isinstance(autor, str):
        autor = [autor]

    return ManifestEntry(
        datei=raw["datei"],
        titel=raw["titel"],
        doc_type=raw["doc_type"],
        bereich=bereich,
        herkunft=raw["herkunft"],
        quelltyp=raw.get("quelltyp", "primaer"),
        thema=thema,
        anlage=anlage,
        projekt=projekt,
        ansprechperson=ansprechperson,
        autor=autor,
        jahr=raw.get("jahr"),
        vertraulichkeit=raw.get("vertraulichkeit", "intern"),
        status=raw.get("status", "final"),
        grad=raw.get("grad"),
        do_ocr=raw.get("do_ocr"),
    )


def load_vokabular(path: Path | None = None) -> dict[str, set[str]]:
    """Laedt vokabular.yaml als Registry.

    Args:
        path: Optionaler Pfad (Default: data/vokabular.yaml).

    Returns:
        Dict mit Facetten-Name -> Set erlaubter Slugs.

    Raises:
        IngestError: Datei nicht gefunden.
    """
    p = path or _VOKABULAR_PATH
    if not p.exists():
        raise IngestError(f"Vokabular nicht gefunden: {p}")
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    registry: dict[str, set[str]] = {}
    for key in ("thema", "anlage", "projekt", "ansprechperson", "autor"):
        section = raw.get(key, {})
        registry[key] = set(section.keys()) if section else set()
    return registry


def validate_manifest_against_vokabular(
    entries: list[ManifestEntry],
    registry: dict[str, set[str]],
) -> None:
    """Validiert alle Manifest-Slugs gegen das Vokabular (Fail-Fast).

    Args:
        entries: Manifest-Eintraege.
        registry: Vokabular-Registry.

    Raises:
        VokabularValidationError: Unbekannter Slug gefunden.
    """
    errors: list[str] = []
    for entry in entries:
        for slug in entry.thema:
            if slug not in registry.get("thema", set()):
                errors.append(
                    f"{entry.datei}: unbekannter thema-Slug '{slug}'"
                )
        for slug in entry.anlage:
            if slug not in registry.get("anlage", set()):
                errors.append(
                    f"{entry.datei}: unbekannter anlage-Slug '{slug}'"
                )
        for slug in entry.projekt:
            if slug not in registry.get("projekt", set()):
                errors.append(
                    f"{entry.datei}: unbekannter projekt-Slug '{slug}'"
                )
        for slug in entry.ansprechperson:
            if slug not in registry.get("ansprechperson", set()):
                errors.append(
                    f"{entry.datei}: unbekannter ansprechperson-Slug '{slug}'"
                )
        for slug in entry.autor:
            if slug not in registry.get("autor", set()):
                errors.append(
                    f"{entry.datei}: unbekannter autor-Slug '{slug}'"
                )
    if errors:
        msg = "Vokabular-Validierung fehlgeschlagen:\n" + "\n".join(errors)
        raise VokabularValidationError(msg)


def validate_enums(entries: list[ManifestEntry]) -> None:
    """Validiert Enum-Felder gegen schema.py (Fail-Fast).

    Args:
        entries: Manifest-Eintraege.

    Raises:
        IngestError: Ungueltiger Enum-Wert.
    """
    errors: list[str] = []
    for entry in entries:
        _check_enum(entry.doc_type, DocType, "doc_type", entry.datei, errors)
        _check_enum(entry.herkunft, Herkunft, "herkunft", entry.datei, errors)
        _check_enum(entry.quelltyp, Quelltyp, "quelltyp", entry.datei, errors)
        _check_enum(
            entry.vertraulichkeit, Vertraulichkeit,
            "vertraulichkeit", entry.datei, errors,
        )
        _check_enum(entry.status, Status, "status", entry.datei, errors)
        if entry.grad:
            _check_enum(entry.grad, Grad, "grad", entry.datei, errors)
        for b in entry.bereich:
            _check_enum(b, Bereich, "bereich", entry.datei, errors)
        for t in entry.thema:
            _check_enum(t, Thema, "thema", entry.datei, errors)
    if errors:
        msg = "Enum-Validierung fehlgeschlagen:\n" + "\n".join(errors)
        raise IngestError(msg)


def _check_enum(
    value: str,
    enum_cls: type[StrEnum],
    field_name: str,
    datei: str,
    errors: list[str],
) -> None:
    """Prueft ob *value* ein gueltiger Enum-Wert ist."""
    valid = {e.value for e in enum_cls}
    if value not in valid:
        errors.append(
            f"{datei}: ungueltiger {field_name}-Wert '{value}' "
            f"(erlaubt: {sorted(valid)})"
        )


def compute_source_hash(path: Path) -> str:
    """Berechnet SHA256-Hash einer Datei.

    Args:
        path: Dateipfad.

    Returns:
        Hex-String des SHA256-Hashs.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def deterministic_chunk_id(source_hash: str, chunk_index: int) -> str:
    """Erzeugt eine deterministische Chunk-ID.

    Re-Export aus ``vector_store.qdrant_client`` fuer Abwaertskompatibilitaet.
    """
    from halle_gehirn.vector_store.qdrant_client import (
        deterministic_chunk_id as _impl,
    )
    return _impl(source_hash, chunk_index)


def build_chunk_payload(
    chunk: Chunk,
    entry: ManifestEntry,
    source_hash: str,
    source_path: str,
    *,
    glossar: dict[str, str] | None = None,
    citations: dict[str, str] | None = None,
    extraction_backend: str = "docling_local",
) -> ChunkPayload:
    """Baut ein ChunkPayload aus Chunk + Manifest-Eintrag.

    Args:
        chunk: Der Chunk.
        entry: Zugehoeriger Manifest-Eintrag.
        source_hash: SHA256 der Quelldatei.
        source_path: Pfad zur Quelldatei.
        glossar: Abkuerzungs-Glossar des Dokuments.
        citations: Zitations-Index des Dokuments.

    Returns:
        Vollstaendiges ChunkPayload.
    """
    source_type = Path(entry.datei).suffix.lstrip(".").lower()
    # text_raw = reiner Chunk-Text (unveraendert)
    # text = suchbarer Text: context_prefix + chunk.text + table_context + captions
    text_for_embedding = chunk.text
    if chunk.context_prefix:
        text_for_embedding = f"{chunk.context_prefix}\n\n{chunk.text}"
    if chunk.table_context:
        text_for_embedding = f"{text_for_embedding}\n\n{chunk.table_context}"
    if chunk.figure_captions:
        caption_block = "\n".join(chunk.figure_captions)
        text_for_embedding = f"{text_for_embedding}\n\n{caption_block}"
    return ChunkPayload(
        text=text_for_embedding,
        text_raw=chunk.text,
        context_prefix=chunk.context_prefix,
        source_url=None,
        source_type=source_type,
        lang="de",
        page=chunk.page,
        table_ref=f"table_{chunk.chunk_index}" if chunk.is_table else None,
        table_context=chunk.table_context,
        chunk_index=chunk.chunk_index,
        # Tabellen-Chunks haben keine echten Body-Offsets (der Chunker
        # setzt lokal 0..len) — None statt irrefuehrender Werte
        char_start=None if chunk.is_table else chunk.char_start,
        char_end=None if chunk.is_table else chunk.char_end,
        ingested_at=datetime.now(tz=UTC).isoformat(),
        source_hash=source_hash,
        titel=entry.titel,
        datei=entry.datei,
        breadcrumb=" > ".join(chunk.headings) if chunk.headings else None,
        doc_type=DocType(entry.doc_type),
        bereich=[Bereich(b) for b in entry.bereich],
        quelltyp=Quelltyp(entry.quelltyp),
        herkunft=Herkunft(entry.herkunft),
        jahr=entry.jahr,
        thema=[Thema(t) for t in entry.thema],
        anlage=entry.anlage,
        projekt=entry.projekt,
        ansprechperson=entry.ansprechperson,
        autor=entry.autor,
        glossar=glossar or {},
        citations=citations or {},
        figure_refs=chunk.figure_refs,
        figure_captions=chunk.figure_captions,
        extraction_backend=extraction_backend,
        vertraulichkeit=Vertraulichkeit(entry.vertraulichkeit),
        status=Status(entry.status),
        grad=Grad(entry.grad) if entry.grad else None,
    )


@dataclass
class _PreparedDoc:
    """Zwischenergebnis je Dokument: extrahiert + gechunkt + gefiltert."""

    entry: ManifestEntry
    source_hash: str
    path: str
    doc: ExtractedDoc
    chunks: list[Chunk]
    glossar: dict[str, str] = field(default_factory=dict)
    citations: dict[str, str] = field(default_factory=dict)
    chunks_before_filter: int = 0


def run_ingest(
    manifest_path: Path | None = None,
    vokabular_path: Path | None = None,
    manual_dir: Path | None = None,
    settings: Settings | None = None,
    selected_dateien: set[str] | None = None,
    skip_hashes: set[str] | None = None,
    on_progress: ProgressCallback = None,
) -> tuple[list[ChunkPayload], IngestStats]:
    """Fuehrt die Ingest-Pipeline aus (ohne Qdrant-Upsert).

    Drei Phasen: (1) Extract + Chunk + Filter je Dokument, (2) Contextual
    Retrieval fuer alle Dokumente (eine async-Phase, graceful bei Ollama-
    Ausfall), (3) Payload-Bau.

    Args:
        manifest_path: Pfad zur manifest.yaml.
        vokabular_path: Pfad zur vokabular.yaml.
        manual_dir: Basisverzeichnis fuer Dokumente.
        settings: Optionale Settings.
        selected_dateien: Optionale Menge von datei-Pfaden. Nur diese
            Dokumente werden verarbeitet. None = alle verarbeiten.
        skip_hashes: Bereits indexierte source_hashes — Dokumente mit
            unveraendertem Hash werden uebersprungen (Delta-Ingest).
        on_progress: Optionaler Callback fuer Fortschrittsereignisse.

    Returns:
        Tuple aus (Liste aller ChunkPayloads, IngestStats).
    """
    t0 = time.monotonic()
    s = settings or get_settings()
    base = manual_dir or _MANUAL_DIR
    entries = load_manifest(manifest_path)

    # Filter auf ausgewaehlte Dokumente
    if selected_dateien is not None:
        entries = [e for e in entries if e.datei in selected_dateien]

    registry = load_vokabular(vokabular_path)
    validate_manifest_against_vokabular(entries, registry)
    validate_enums(entries)
    logger.info("ingest_validated", docs=len(entries))

    docling = DoclingExtractor(settings=s)
    plaintext = PlaintextExtractor()
    extractors: dict[str, Extractor] = {}
    for ext in docling.supported_extensions:
        extractors[ext] = docling
    for ext in plaintext.supported_extensions:
        extractors[ext] = plaintext

    chunker = MarkdownChunker(settings=s)
    stats = IngestStats(docs_total=len(entries))

    # Phase 1: Extract + Chunk + Filter
    prepared = _prepare_all(
        entries, base, extractors, chunker, s, skip_hashes, stats,
        on_progress=on_progress, t0=t0,
    )

    # Phase 2: Contextual Retrieval (eine async-Phase fuer alle Dokumente)
    if s.use_contextual_retrieval and prepared:
        if on_progress:
            on_progress(ProgressEvent(
                phase="enrich",
                datei="(alle)",
                doc_index=0,
                doc_total=len(prepared),
                detail=f"Kontextanreicherung fuer {len(prepared)} Dokumente...",
                elapsed_s=time.monotonic() - t0,
            ))
        _run_enrichment(prepared, s)

    # Phase 3: Payloads bauen
    all_payloads: list[ChunkPayload] = []
    for prep in prepared:
        backend = prep.doc.meta.get(
            "extraction_backend", "docling_local",
        )
        payloads = [
            build_chunk_payload(
                chunk, prep.entry, prep.source_hash, prep.path,
                glossar=prep.glossar, citations=prep.citations,
                extraction_backend=backend,
            )
            for chunk in prep.chunks
        ]
        all_payloads.extend(payloads)
        stats.chunks_total += len(payloads)
        if payloads:
            stats.docs_success += 1
            logger.info(
                "ingest_doc_processed",
                datei=prep.entry.datei,
                chunks=len(payloads),
                hash=prep.source_hash[:12],
            )
        else:
            stats.docs_filtered_empty += 1
            stats.errors.append(
                f"{prep.entry.datei}: 0 Chunks nach Filter "
                f"(Body: {len(prep.doc.body_md)} Zeichen)"
            )
            logger.warning(
                "ingest_doc_filtered_empty",
                datei=prep.entry.datei,
                body_chars=len(prep.doc.body_md),
                chunks_before_filter=prep.chunks_before_filter,
                hash=prep.source_hash[:12],
            )

    logger.info(
        "ingest_done",
        total=stats.docs_total,
        success=stats.docs_success,
        skipped=stats.docs_skipped,
        unchanged=stats.docs_unchanged,
        failed=stats.docs_failed,
        filtered_empty=stats.docs_filtered_empty,
        chunks=stats.chunks_total,
    )
    return all_payloads, stats


def _prepare_all(
    entries: list[ManifestEntry],
    base_dir: Path,
    extractors: dict[str, Extractor],
    chunker: MarkdownChunker,
    settings: Settings,
    skip_hashes: set[str] | None,
    stats: IngestStats,
    on_progress: ProgressCallback = None,
    t0: float = 0.0,
) -> list[_PreparedDoc]:
    """Phase 1: Extrahiert, chunked und filtert alle Eintraege."""
    prepared: list[_PreparedDoc] = []
    total = len(entries)
    chunks_so_far = 0

    for idx, entry in enumerate(entries, 1):
        if on_progress:
            on_progress(ProgressEvent(
                phase="extract",
                datei=entry.datei,
                doc_index=idx,
                doc_total=total,
                detail=f"Extrahiere {entry.datei}...",
                chunks_so_far=chunks_so_far,
                elapsed_s=time.monotonic() - t0,
            ))
        try:
            prep = _prepare_entry(
                entry, base_dir, extractors, chunker, settings, skip_hashes,
            )
        except FileNotFoundError as exc:
            stats.docs_skipped += 1
            stats.errors.append(f"{entry.datei}: {exc}")
            logger.warning("ingest_doc_skipped", datei=entry.datei, error=str(exc))
            continue
        except Exception as exc:
            stats.docs_failed += 1
            stats.errors.append(f"{entry.datei}: {exc}")
            logger.error("ingest_doc_failed", datei=entry.datei, error=str(exc))
            continue

        if prep is None:
            stats.docs_unchanged += 1
            continue
        prepared.append(prep)
        chunks_so_far += len(prep.chunks)

        # Fortschritt nach dem Chunking
        if on_progress:
            _emit_chunk_progress(
                on_progress, prep, idx, total, chunks_so_far, t0,
            )
    return prepared


def _emit_chunk_progress(
    cb: Any,
    prep: _PreparedDoc,
    doc_index: int,
    doc_total: int,
    chunks_so_far: int,
    t0: float,
) -> None:
    """Emittiert ein Fortschrittsereignis nach dem Chunking."""
    chunks = prep.chunks
    doc = prep.doc
    # Zufaelliger Sample-Chunk
    sample: Chunk | None = None
    if chunks:
        sample = random.choice(chunks)
    # Strategie-Zusammenfassung
    table_count = sum(1 for c in chunks if c.is_table)
    body_count = len(chunks) - table_count
    strategy = f"{body_count} Body + {table_count} Tabellen"
    # Abbildungen
    fig_count = len(doc.figures)
    fig_paths = [f.image_path for f in doc.figures if f.image_path]
    # Extraktions-Metadaten
    backend = doc.meta.get("extraction_backend", "docling_local")
    ocr_retry = doc.meta.get("ocr_retry") == "true"
    file_size = int(doc.meta.get("file_size_bytes", 0))

    cb(ProgressEvent(
        phase="chunk",
        datei=prep.entry.datei,
        doc_index=doc_index,
        doc_total=doc_total,
        detail=f"{len(chunks)} Chunks erzeugt ({strategy})",
        chunks_so_far=chunks_so_far,
        chunks_total=len(chunks),
        sample_chunk=sample.text[:300] if sample else None,
        sample_heading=(
            " > ".join(sample.headings) if sample and sample.headings else None
        ),
        strategy=strategy,
        figures_count=fig_count,
        figure_paths=fig_paths[:5],
        elapsed_s=time.monotonic() - t0,
        body_chars=len(doc.body_md),
        tables_count=len(doc.tables),
        chunks_before_filter=prep.chunks_before_filter,
        extraction_backend=backend,
        ocr_retry=ocr_retry,
        file_size_bytes=file_size,
    ))


def _prepare_entry(
    entry: ManifestEntry,
    base_dir: Path,
    extractors: dict[str, Extractor],
    chunker: MarkdownChunker,
    settings: Settings | None = None,
    skip_hashes: set[str] | None = None,
) -> _PreparedDoc | None:
    """Extrahiert, chunked und filtert einen Manifest-Eintrag.

    Returns:
        _PreparedDoc — oder None, wenn der source_hash bereits indexiert
        ist (Delta-Ingest: Dokument unveraendert, Extraktion uebersprungen).
    """
    path = base_dir / entry.datei
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    suffix = path.suffix.lower()
    extractor = extractors.get(suffix)
    if extractor is None:
        supported = sorted(extractors.keys())
        raise ExtractionError(
            f"Nicht unterstuetztes Format: {suffix} "
            f"(erlaubt: {supported})"
        )
    # Hash VOR der (teuren) Extraktion — Delta-Skip spart Docling-Lauf
    source_hash = compute_source_hash(path)
    if skip_hashes is not None and source_hash in skip_hashes:
        logger.info(
            "ingest_doc_unchanged",
            datei=entry.datei,
            hash=source_hash[:12],
        )
        return None
    logger.info(
        "ingest_doc_start",
        datei=entry.datei,
        suffix=suffix,
        extractor=type(extractor).__name__,
        size_bytes=path.stat().st_size,
    )
    # Per-Dokument-OCR-Override aus Manifest durchreichen
    if (
        entry.do_ocr is not None
        and isinstance(extractor, DoclingExtractor)
    ):
        doc: ExtractedDoc = extractor.extract(path, do_ocr=entry.do_ocr)
    else:
        doc = extractor.extract(path)
    # Kuratierter Manifest-Titel ist die Quelle der Wahrheit (wie im
    # ManualLoader-Fluss) — wichtig u.a. fuer den Kontext-Prompt.
    doc.title = entry.titel
    # Extraktions-Artefakte bereinigen (OCR-Fehler, Ligatur-Verluste,
    # getrennte Diakritika) BEVOR Glossar/Chunking/Embeddings laufen.
    # Body als Selbstreferenz-Corpus: bei pymupdf4llm-Fallback liegen
    # Tabellen inline im body_md — Regel 6b braucht den Corpus-Lookup.
    doc.body_md, _ = sanitize_text(
        doc.body_md, source=entry.datei, corpus=doc.body_md,
    )
    for tbl in doc.tables:
        tbl.markdown, _ = sanitize_text(
            tbl.markdown, source=entry.datei, corpus=doc.body_md,
        )
    # Glossar + Zitations-Index VOR dem Chunking extrahieren (die Sections
    # werden spaeter vom Filter gedroppt, aber die Daten sind bereits gesichert)
    glossar = parse_glossar(doc.body_md)
    citations = parse_citations(doc.body_md)
    logger.info(
        "ingest_doc_extracted",
        datei=entry.datei,
        title=doc.title,
        body_chars=len(doc.body_md),
        tables=len(doc.tables),
        source_type=doc.source_type,
    )
    chunks: list[Chunk] = chunker.chunk(doc, doc_type=entry.doc_type)
    chunks_before_filter = len(chunks)
    chunks = filter_chunks(chunks, doc_type=entry.doc_type, settings=settings)
    _check_chunk_plausibility(chunks, doc, entry.datei, settings)
    link_figures_to_chunks(chunks, doc.figures)
    _link_table_context(chunks, doc)
    return _PreparedDoc(
        entry=entry,
        source_hash=source_hash,
        path=str(path),
        doc=doc,
        chunks=chunks,
        glossar=glossar,
        citations=citations,
        chunks_before_filter=chunks_before_filter,
    )


def _check_chunk_plausibility(
    chunks: list[Chunk],
    doc: ExtractedDoc,
    datei: str,
    settings: Settings,
) -> None:
    """Zweistufige Plausibilitaetspruefung der Chunk-Anzahl.

    Stufe 1 (Warnung): Mehr als ``chunks_per_page_warn`` Chunks/Seite.
    Stufe 2 (Abbruch): Mehr als ``chunks_per_page_abort`` Chunks/Seite
    → ``ChunkExplosionError``, Dokument wird NICHT indexiert.

    Args:
        chunks: Gefilterte Chunks.
        doc: Extrahiertes Dokument (fuer page_count).
        datei: Dateiname (fuer Logging).
        settings: Config mit Schwellenwerten.

    Raises:
        ChunkExplosionError: Chunk-Dichte ueber Abbruch-Schwelle.
    """
    page_count = doc.page_count
    if not page_count or page_count < 1:
        return  # Keine Seiteninfo → Check nicht moeglich
    ratio = len(chunks) / page_count
    if ratio > settings.chunks_per_page_abort:
        logger.error(
            "chunk_explosion_abort",
            datei=datei,
            chunks=len(chunks),
            pages=page_count,
            ratio=round(ratio, 1),
            threshold=settings.chunks_per_page_abort,
        )
        raise ChunkExplosionError(
            f"Chunk-Explosion für {datei}: "
            f"{len(chunks)} Chunks bei {page_count} Seiten "
            f"({ratio:.1f} Chunks/Seite, Abbruch-Schwelle: "
            f"{settings.chunks_per_page_abort}). "
            f"Dokument wird nicht indexiert."
        )
    if ratio > settings.chunks_per_page_warn:
        logger.warning(
            "chunk_density_high",
            datei=datei,
            chunks=len(chunks),
            pages=page_count,
            ratio=round(ratio, 1),
            threshold=settings.chunks_per_page_warn,
        )


def _run_enrichment(prepared: list[_PreparedDoc], settings: Settings) -> None:
    """Phase 2: Contextual Retrieval — sync-Wrapper um die async-Phase.

    Graceful Degradation: Jeder Fehler (Ollama down, laufender Event-Loop)
    degradiert zu context_prefix=None statt den Ingest abzubrechen.
    """
    try:
        asyncio.run(_enrich_prepared(prepared, settings))
    except RuntimeError as exc:
        # z.B. bereits laufender Event-Loop im Aufrufer-Kontext
        logger.warning("context_enrichment_skipped", reason=str(exc))


def _link_table_context(chunks: list[Chunk], doc: ExtractedDoc) -> None:
    """Baut Caption-Zuordnung und verknuepft Tabellen mit Body-Kontext."""
    table_chunks = [c for c in chunks if c.is_table]
    if not table_chunks or not doc.tables:
        return
    # Jeder Tabellen-Chunk dem Quell-TableBlock zuordnen (ueber Header-Zeile)
    captions: list[str | None] = []
    for tc in table_chunks:
        first_line = tc.text.split("\n")[0].strip()
        matched_caption: str | None = None
        for tbl in doc.tables:
            tbl_first = tbl.markdown.strip().split("\n")[0].strip()
            if first_line == tbl_first:
                matched_caption = tbl.caption
                break
        captions.append(matched_caption)
    link_tables_to_chunks(chunks, captions)


async def _enrich_prepared(
    prepared: list[_PreparedDoc], settings: Settings,
) -> None:
    """Reichert alle vorbereiteten Dokumente per Contextual Retrieval an."""
    enricher = OllamaContextEnricher(settings=settings)
    for prep in prepared:
        try:
            await enricher.enrich(prep.chunks, prep.doc)
        except Exception as exc:
            # Belt-and-braces: enrich() faengt Chunk-Fehler bereits intern
            logger.warning(
                "context_enrichment_doc_failed",
                datei=prep.entry.datei,
                error=str(exc),
            )
