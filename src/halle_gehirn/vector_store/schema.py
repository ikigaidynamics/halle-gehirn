"""Collection- und Payload-Schema für `halle_wissen`.

Vereint das Qdrant-Hybrid-Setup (Named Vectors dense+sparse, Quantization) mit
der Halle-Taxonomie (Facetten + kontrolliertes Vokabular). Siehe docs/taxonomie.md
für die inhaltliche Herleitung und data/vokabular.yaml für die wachsenden Facetten
(anlage / projekt / ansprechperson).

Grundsatz: Facetten statt Ordner. Ein Chunk ist über orthogonale Metadaten
beschrieben; die „Verschachtelung" entsteht zur Abfragezeit über Filter-
Kombinationen (Self-Querying), nicht über einen Speicherbaum.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    PayloadSchemaType,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    SparseVectorParams,
    VectorParams,
)

from halle_gehirn.config import get_settings


# ────────────────────────── Geschlossene Facetten ──────────────────────────
class Bereich(StrEnum):
    """Die „Dreifaltigkeit" + Infrastruktur (mehrwertig)."""

    TRANSFER = "transfer"
    FORSCHUNG = "forschung"
    LEHRE = "lehre"
    INFRASTRUKTUR = "infrastruktur"


class Thema(StrEnum):
    """Offizielle Forschungsschwerpunkte des Lehrstuhls (mehrwertig)."""

    MRK = "mensch_roboter_kollaboration"
    MMI = "mensch_maschine_interaktion"  # Simulationsgestützte MMI
    VST = "vernetzte_steuerungstechnik"


class DocType(StrEnum):
    """Semantische Dokumentsorte (einwertig)."""

    ABSCHLUSSARBEIT = "abschlussarbeit"
    PROMOTION = "promotion"
    PROJEKTBERICHT = "projektbericht"
    ANLAGENDOKU = "anlagendoku"
    HANDBUCH = "handbuch"
    FLYER = "flyer"
    ONLINE_BEITRAG = "online_beitrag"
    WORKSHOP_SLIDES = "workshop_slides"
    LEHRBUCH = "lehrbuch"
    EXPERTEN_TRANSKRIPT = "experten_transkript"
    VIDEO_TRANSKRIPT = "video_transkript"
    ZUSAMMENFASSUNG = "zusammenfassung"
    SONSTIGES = "sonstiges"


class Quelltyp(StrEnum):
    """Provenienz / Vertrauensstufe (einwertig). Speist Ampel & Zitate."""

    PRIMAER = "primaer"
    KURATIERT = "kuratiert"
    SYNTHETISCH = "synthetisch"


class Herkunft(StrEnum):
    """Ownership / produzierende Einheit (einwertig)."""

    LEHRSTUHL_AT = "lehrstuhl_at"
    MDZ = "mdz"
    EDIH = "edih"
    BTU = "btu"
    EXTERN = "extern"


class Vertraulichkeit(StrEnum):
    """Zugriffs-/Governance-Stufe (vorgezogen, Default intern)."""

    OFFEN = "offen"
    INTERN = "intern"
    VERTRAULICH = "vertraulich"


class Grad(StrEnum):
    """Nur bei doc_type == ABSCHLUSSARBEIT."""

    BACHELOR = "bachelor"
    MASTER = "master"


class Status(StrEnum):
    FINAL = "final"
    IN_ARBEIT = "in_arbeit"


# ────────────────────────── Payload je Chunk ──────────────────────────
class ChunkPayload(BaseModel):
    """Vollständiges Payload je Chunk.

    Auto-Felder füllt die Pipeline; Kurations-Felder kommen aus
    data/manifest.yaml. Wachsende Facetten (anlage/projekt/ansprechperson)
    sind Registry-validierte Slugs (data/vokabular.yaml).
    """

    # — Inhalt (Auto) —
    text: str
    text_raw: str
    context_prefix: str | None = None
    # — Technik/Herkunft (Auto) —
    source_url: str | None = None
    source_type: str  # pdf|docx|pptx|html|manual|transcript|audio
    lang: str = "de"
    page: int | None = None
    table_ref: str | None = None
    table_context: str | None = None
    chunk_index: int
    # None bei Tabellen-Chunks (keine echten Body-Offsets)
    char_start: int | None = None
    char_end: int | None = None
    ingested_at: str
    source_hash: str
    # — Titel/Navigation —
    titel: str
    datei: str = ""
    breadcrumb: str | None = None
    # — Semantische Facetten (Kuration, indiziert) —
    doc_type: DocType
    bereich: list[Bereich]
    quelltyp: Quelltyp
    herkunft: Herkunft
    jahr: int | None = None
    thema: list[Thema] = Field(default_factory=list)
    anlage: list[str] = Field(default_factory=list)
    projekt: list[str] = Field(default_factory=list)
    ansprechperson: list[str] = Field(default_factory=list)
    autor: list[str] = Field(default_factory=list)
    # — Dokument-Metadaten (Glossar, Zitationen) —
    glossar: dict[str, str] = Field(default_factory=dict)
    citations: dict[str, str] = Field(default_factory=dict)
    # — Abbildungen —
    figure_refs: list[str] = Field(default_factory=list)
    figure_captions: list[str] = Field(default_factory=list)
    figure_description: str | None = None  # Reserviert fuer VLM, jetzt None
    # — Extraktion —
    extraction_backend: str = "docling_local"
    # — Governance (vorgezogen) —
    vertraulichkeit: Vertraulichkeit = Vertraulichkeit.INTERN
    status: Status = Status.FINAL
    grad: Grad | None = None


# ────────────────────────── Qdrant-Schema ──────────────────────────
# KEYWORD-Index matcht auch Array-Felder (Match auf jedes Element).
KEYWORD_FELDER: tuple[str, ...] = (
    "doc_type",
    "bereich",
    "thema",
    "quelltyp",
    "herkunft",
    "anlage",
    "projekt",
    "ansprechperson",
    "autor",
    "vertraulichkeit",
    "status",
    "grad",
    "lang",
    "source_type",
)


def create_collection_if_missing(client: QdrantClient) -> None:
    """Legt `halle_wissen` mit Named Vectors (dense+sparse), Quantization und
    allen Payload-Indizes an — idempotent."""
    s = get_settings()
    if client.collection_exists(s.qdrant_collection):
        return

    client.create_collection(
        collection_name=s.qdrant_collection,
        vectors_config={
            "dense": VectorParams(size=s.embedding_dim, distance=Distance.COSINE),
            # optional: "colbert" (MultiVector MAX_SIM) bei USE_COLBERT
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(modifier=Modifier.IDF),
        },
        quantization_config=ScalarQuantization(
            scalar=ScalarQuantizationConfig(type=ScalarType.INT8, always_ram=True),
        ),
    )
    create_payload_indices(client)


def create_payload_indices(client: QdrantClient) -> None:
    """Legt die Payload-Indizes für gefilterte Suche + Self-Querying an."""
    s = get_settings()
    for feld in KEYWORD_FELDER:
        client.create_payload_index(s.qdrant_collection, feld, PayloadSchemaType.KEYWORD)
    client.create_payload_index(s.qdrant_collection, "jahr", PayloadSchemaType.INTEGER)
