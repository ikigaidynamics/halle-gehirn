"""Admin-Router fuer Wissensbestand-Verwaltung (/admin/wissen).

9 Endpoints: Bestand-Uebersicht, Vokabular-CRUD, Dokument-Upload/-Detect/-Delete,
Ingest-Start/-Status/-Stream. Alle auth-geschuetzt via X-API-Key.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from starlette.responses import StreamingResponse

from halle_gehirn.api.admin_schemas import (
    BestandResponse,
    ChunkDetailResponse,
    DokumentChunksResponse,
    DokumentCreateResponse,
    DokumentDeleteResponse,
    IndexedDocResponse,
    IngestJobStatus,
    IngestStartRequest,
    IngestStartResponse,
    ManifestEntryResponse,
    MetadataSuggestionResponse,
    VokabularCreateRequest,
    VokabularCreateResponse,
    VokabularResponse,
)
from halle_gehirn.api.ingest_jobs import create_job, get_job, start_job
from halle_gehirn.api.routes.admin import verify_api_key
from halle_gehirn.extraction.metadata_detector import (
    detect_metadata,
    extract_text_from_upload,
)
from halle_gehirn.manifest.editor import (
    ENUM_LABELS,
    delete_manifest_entry,
    list_upload_sorten,
    load_manifest_entries,
    load_vokabular_choices,
    save_manifest_entry,
    save_uploaded_file,
    save_vokabular_entry,
    validate_entry,
)
from halle_gehirn.pipeline.ingest import ManifestEntry, compute_source_hash
from halle_gehirn.vector_store.qdrant_client import (
    delete_by_source_hash,
    get_chunks_by_datei,
    list_indexed_documents,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin/wissen", tags=["admin-wissen"])

_MANUAL_DIR = Path("data/manual")


# ── GET /bestand ──


@router.get("/bestand", response_model=BestandResponse)
async def get_bestand(
    _key: Annotated[str, Depends(verify_api_key)],
) -> BestandResponse:
    """Liefert Manifest-Eintraege + Qdrant-Status als Bestandsuebersicht."""
    entries = load_manifest_entries()
    indexed = list_indexed_documents()
    indexed_by_datei: dict[str, dict[str, Any]] = {
        d["datei"]: d for d in indexed
    }

    manifest_resp: list[ManifestEntryResponse] = []
    for e in entries:
        file_path = _MANUAL_DIR / e.datei
        manifest_resp.append(ManifestEntryResponse(
            datei=e.datei,
            titel=e.titel,
            doc_type=e.doc_type,
            doc_type_label=ENUM_LABELS.get(e.doc_type, e.doc_type),
            bereich=e.bereich,
            bereich_labels=[ENUM_LABELS.get(b, b) for b in e.bereich],
            herkunft=e.herkunft,
            herkunft_label=ENUM_LABELS.get(e.herkunft, e.herkunft),
            quelltyp=e.quelltyp,
            vertraulichkeit=e.vertraulichkeit,
            vertraulichkeit_label=ENUM_LABELS.get(
                e.vertraulichkeit, e.vertraulichkeit,
            ),
            status=e.status,
            jahr=e.jahr,
            grad=e.grad,
            thema=e.thema,
            anlage=e.anlage,
            projekt=e.projekt,
            ansprechperson=e.ansprechperson,
            autor=e.autor,
            file_exists=file_path.exists(),
            is_indexed=e.datei in indexed_by_datei,
        ))

    manifest_dateien = {e.datei for e in entries}
    indexed_resp: list[IndexedDocResponse] = []
    total_chunks = 0
    for doc in indexed:
        total_chunks += doc.get("chunk_count", 0)
        indexed_resp.append(IndexedDocResponse(
            datei=doc.get("datei", ""),
            titel=doc.get("titel", ""),
            chunk_count=doc.get("chunk_count", 0),
            source_hash=doc.get("source_hash", ""),
            doc_type=doc.get("doc_type", ""),
            in_manifest=doc.get("datei", "") in manifest_dateien,
        ))

    return BestandResponse(
        manifest_entries=manifest_resp,
        indexed_docs=indexed_resp,
        total_chunks=total_chunks,
    )


# ── GET /vokabular ──


@router.get("/vokabular", response_model=VokabularResponse)
async def get_vokabular(
    _key: Annotated[str, Depends(verify_api_key)],
) -> VokabularResponse:
    """Liefert alle Facetten-Choices + verfuegbare Upload-Sorten."""
    return VokabularResponse(
        choices=load_vokabular_choices(),
        sorten=list_upload_sorten(),
    )


# ── POST /vokabular ──

_REGISTRY_FACETS = {"thema", "anlage", "projekt", "ansprechperson", "autor"}


@router.post("/vokabular", response_model=VokabularCreateResponse)
async def create_vokabular(
    body: VokabularCreateRequest,
    _key: Annotated[str, Depends(verify_api_key)],
) -> VokabularCreateResponse:
    """Legt einen neuen Facettenwert in vokabular.yaml an."""
    if body.facet not in _REGISTRY_FACETS:
        raise HTTPException(
            status_code=422,
            detail=f"Facet '{body.facet}' nicht erlaubt. "
            f"Erlaubt: {sorted(_REGISTRY_FACETS)}",
        )
    try:
        save_vokabular_entry(body.facet, body.slug, body.label)
    except ValueError as exc:
        status = 409 if "existiert bereits" in str(exc) else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return VokabularCreateResponse(
        facet=body.facet, slug=body.slug, label=body.label,
    )


# ── POST /dokumente ──


@router.post("/dokumente", response_model=DokumentCreateResponse)
async def create_dokument(
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str, Form()],
    _key: Annotated[str, Depends(verify_api_key)],
) -> DokumentCreateResponse:
    """Laedt ein Dokument hoch und speichert es mit Metadaten."""
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=422, detail=f"metadata ist kein gueltiges JSON: {exc}",
        ) from exc

    sorte = meta.pop("sorte", None)
    if not sorte:
        raise HTTPException(status_code=422, detail="'sorte' fehlt in metadata.")

    entry = ManifestEntry(
        datei=f"{sorte}/{file.filename}",
        titel=meta.get("titel", file.filename or ""),
        doc_type=meta.get("doc_type", "sonstiges"),
        bereich=meta.get("bereich", []),
        herkunft=meta.get("herkunft", "lehrstuhl_at"),
        quelltyp=meta.get("quelltyp", "primaer"),
        vertraulichkeit=meta.get("vertraulichkeit", "intern"),
        status=meta.get("status", "final"),
        jahr=meta.get("jahr"),
        grad=meta.get("grad"),
        thema=meta.get("thema", []),
        anlage=meta.get("anlage", []),
        projekt=meta.get("projekt", []),
        ansprechperson=meta.get("ansprechperson", []),
        autor=meta.get("autor", []),
    )

    errors = validate_entry(entry)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    file_data = await file.read()
    try:
        save_uploaded_file(file_data, file.filename or "upload", sorte)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    save_manifest_entry(entry)
    logger.info("dokument_created", datei=entry.datei)
    return DokumentCreateResponse(datei=entry.datei, titel=entry.titel)


# ── POST /dokumente/detect ──


@router.post("/dokumente/detect", response_model=MetadataSuggestionResponse)
async def detect_dokument_metadata(
    file: Annotated[UploadFile, File()],
    _key: Annotated[str, Depends(verify_api_key)],
) -> MetadataSuggestionResponse:
    """Erkennt Metadaten aus Dateiname + extrahiertem Text."""
    file_data = await file.read()
    text = extract_text_from_upload(file_data, file.filename or "upload")
    choices = load_vokabular_choices()
    s = detect_metadata(file.filename or "upload", text, choices)
    return MetadataSuggestionResponse(
        titel=s.titel,
        doc_type=s.doc_type,
        grad=s.grad,
        bereich=s.bereich,
        herkunft=s.herkunft,
        quelltyp=s.quelltyp,
        vertraulichkeit=s.vertraulichkeit,
        status=s.status,
        jahr=s.jahr,
        sorte=s.sorte,
        autor_vorschlag=s.autor_vorschlag,
        ansprechperson_vorschlag=s.ansprechperson_vorschlag,
        studiengang=s.studiengang,
    )


# ── DELETE /dokumente/{datei:path} ──


@router.delete(
    "/dokumente/{datei:path}", response_model=DokumentDeleteResponse,
)
async def delete_dokument(
    datei: str,
    _key: Annotated[str, Depends(verify_api_key)],
    delete_file: bool = False,
) -> DokumentDeleteResponse:
    """Loescht Dokument aus Manifest und Qdrant (immer beides)."""
    file_path = _MANUAL_DIR / datei

    deleted_chunks = 0
    deleted_from_qdrant = False
    if file_path.exists():
        source_hash = compute_source_hash(file_path)
        try:
            for doc in list_indexed_documents():
                if doc.get("source_hash") == source_hash:
                    deleted_chunks = doc.get("chunk_count", 0)
                    break
            delete_by_source_hash(source_hash)
            deleted_from_qdrant = True
        except Exception as exc:
            logger.warning(
                "qdrant_delete_failed", datei=datei, error=str(exc),
            )

    deleted_from_manifest = delete_manifest_entry(
        datei, delete_file=delete_file,
    )

    file_deleted = delete_file and not file_path.exists()

    return DokumentDeleteResponse(
        datei=datei,
        deleted_from_manifest=deleted_from_manifest,
        deleted_from_qdrant=deleted_from_qdrant,
        deleted_chunks=deleted_chunks,
        deleted_file=file_deleted,
    )


# ── GET /dokumente/{datei}/chunks ──


@router.get(
    "/dokumente/{datei:path}/chunks",
    response_model=DokumentChunksResponse,
)
async def get_dokument_chunks(
    datei: str,
    _key: Annotated[str, Depends(verify_api_key)],
) -> DokumentChunksResponse:
    """Liefert alle Chunks eines Dokuments aus Qdrant (Diagnose-Ansicht)."""
    raw_chunks = get_chunks_by_datei(datei)
    if not raw_chunks:
        raise HTTPException(
            status_code=404,
            detail=f"Keine Chunks fuer '{datei}' in Qdrant gefunden.",
        )

    titel = ""
    details: list[ChunkDetailResponse] = []
    for item in raw_chunks:
        p = item.get("payload", {})
        if not titel:
            titel = p.get("titel", "")
        text = p.get("text", "")
        details.append(ChunkDetailResponse(
            chunk_index=p.get("chunk_index", 0),
            breadcrumb=p.get("breadcrumb"),
            context_prefix=p.get("context_prefix"),
            text=text,
            page=p.get("page"),
            is_table=p.get("table_ref") is not None,
            token_count=len(text.split()),
        ))

    return DokumentChunksResponse(
        datei=datei,
        titel=titel,
        chunk_count=len(details),
        chunks=details,
    )


# ── POST /ingest ──


@router.post("/ingest", response_model=IngestStartResponse)
async def start_ingest(
    body: IngestStartRequest,
    _key: Annotated[str, Depends(verify_api_key)],
) -> IngestStartResponse:
    """Startet einen Ingest-Job fuer ausgewaehlte Dokumente."""
    if not body.selected_dateien:
        raise HTTPException(
            status_code=422, detail="selected_dateien darf nicht leer sein.",
        )
    job_id = create_job()
    start_job(job_id, body.selected_dateien, reset=body.reset_collection)
    logger.info(
        "ingest_started", job_id=job_id, dateien=len(body.selected_dateien),
    )
    return IngestStartResponse(
        job_id=job_id,
        message=f"Ingest gestartet fuer {len(body.selected_dateien)} Dokument(e).",
    )


# ── GET /ingest/{job_id} ──


@router.get("/ingest/{job_id}", response_model=IngestJobStatus)
async def get_ingest_status(
    job_id: str,
    _key: Annotated[str, Depends(verify_api_key)],
) -> IngestJobStatus:
    """Liefert den aktuellen Status eines Ingest-Jobs (Polling-Fallback)."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404, detail=f"Job '{job_id}' nicht gefunden.",
        )
    last = job.events[-1] if job.events else {}
    doc_total = last.get("doc_total", 1) or 1
    progress = last.get("doc_index", 0) / doc_total
    if job.status == "completed":
        progress = 1.0

    return IngestJobStatus(
        job_id=job.job_id,
        status=job.status,
        progress=round(progress, 3),
        phase=last.get("phase", ""),
        current_datei=last.get("datei", ""),
        detail=last.get("detail", ""),
        stats=job.stats,
        error=job.error,
    )


# ── GET /ingest/{job_id}/stream ──


@router.get("/ingest/{job_id}/stream")
async def stream_ingest_progress(
    job_id: str,
    _key: Annotated[str, Depends(verify_api_key)],
) -> StreamingResponse:
    """Streamt Ingest-Fortschritt als Server-Sent Events."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404, detail=f"Job '{job_id}' nicht gefunden.",
        )

    async def event_generator() -> AsyncIterator[str]:
        cursor = 0
        while True:
            new_events = job.events_since(cursor)
            for event in new_events:
                line = json.dumps(event, ensure_ascii=False)
                yield f"data: {line}\n\n"
                cursor += 1
                if event.get("status") in ("completed", "failed"):
                    return

            if job.status in ("completed", "failed") and cursor >= job.event_count():
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
