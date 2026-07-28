"""Pydantic-Schemas fuer /admin/wissen Endpoints.

Definiert Request/Response-Modelle fuer Bestandsverwaltung,
Vokabular-CRUD, Dokument-Upload/-Delete und Ingest-Jobs.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# ── Bestand ──


class ManifestEntryResponse(BaseModel):
    """Ein Dokument aus manifest.yaml mit aufgeloesten Labels."""

    datei: str
    titel: str
    doc_type: str
    doc_type_label: str = ""
    bereich: list[str] = Field(default_factory=list)
    bereich_labels: list[str] = Field(default_factory=list)
    herkunft: str = ""
    herkunft_label: str = ""
    quelltyp: str = ""
    vertraulichkeit: str = ""
    vertraulichkeit_label: str = ""
    status: str = ""
    jahr: int | None = None
    grad: str | None = None
    thema: list[str] = Field(default_factory=list)
    anlage: list[str] = Field(default_factory=list)
    projekt: list[str] = Field(default_factory=list)
    ansprechperson: list[str] = Field(default_factory=list)
    autor: list[str] = Field(default_factory=list)
    file_exists: bool = False
    is_indexed: bool = False


class IndexedDocResponse(BaseModel):
    """Ein in Qdrant indexiertes Dokument."""

    datei: str
    titel: str = ""
    chunk_count: int = 0
    source_hash: str = ""
    doc_type: str = ""
    in_manifest: bool = False


class BestandResponse(BaseModel):
    """Kombiniert Manifest-Eintraege + Qdrant-Status."""

    manifest_entries: list[ManifestEntryResponse] = Field(default_factory=list)
    indexed_docs: list[IndexedDocResponse] = Field(default_factory=list)
    total_chunks: int = 0


# ── Vokabular ──


class VokabularResponse(BaseModel):
    """Alle Facetten-Choices + verfuegbare Upload-Sorten."""

    choices: dict[str, dict[str, str]] = Field(default_factory=dict)
    sorten: list[str] = Field(default_factory=list)


class VokabularCreateRequest(BaseModel):
    """Neuen Facettenwert anlegen."""

    facet: str
    slug: str
    label: str


class VokabularCreateResponse(BaseModel):
    """Bestaetigung eines neuen Facettenwerts."""

    status: str = "ok"
    facet: str
    slug: str
    label: str


# ── Dokumente ──


class DokumentCreateResponse(BaseModel):
    """Bestaetigung eines neu angelegten Dokuments."""

    status: str = "ok"
    datei: str
    titel: str


class MetadataSuggestionResponse(BaseModel):
    """Auto-erkannte Metadaten-Vorschlaege fuer ein hochgeladenes Dokument."""

    titel: str = ""
    doc_type: str | None = None
    grad: str | None = None
    bereich: list[str] = Field(default_factory=list)
    herkunft: str = ""
    quelltyp: str = ""
    vertraulichkeit: str = ""
    status: str = ""
    jahr: int | None = None
    sorte: str | None = None
    autor_vorschlag: str | None = None
    ansprechperson_vorschlag: list[str] = Field(default_factory=list)
    studiengang: str | None = None


class DokumentDeleteResponse(BaseModel):
    """Ergebnis einer Dokument-Loeschung."""

    status: str = "ok"
    datei: str
    deleted_from_manifest: bool = False
    deleted_from_qdrant: bool = False
    deleted_chunks: int = 0
    deleted_file: bool = False


# ── Ingest ──


class IngestStartRequest(BaseModel):
    """Startet einen Ingest-Job fuer ausgewaehlte Dokumente."""

    selected_dateien: list[str]
    reset_collection: bool = False


class IngestStartResponse(BaseModel):
    """Bestaetigung eines gestarteten Ingest-Jobs."""

    status: str = "accepted"
    job_id: str
    message: str = ""


class IngestJobStatus(BaseModel):
    """Aktueller Status eines laufenden/abgeschlossenen Ingest-Jobs."""

    job_id: str
    status: str = "running"
    progress: float = 0.0
    phase: str = ""
    current_datei: str = ""
    detail: str = ""
    stats: dict | None = None
    error: str | None = None
