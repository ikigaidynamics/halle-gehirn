"""Chunk-Qualitaets-Audit fuer indexierte Qdrant-Chunks.

Liest Chunks direkt aus der Collection, wendet deterministische Red-Flag-
Regeln an und optional einen LLM-Judge (Ollama). Produziert einen Report
mit Drop-Kandidaten — loescht selbst NICHTS.

Phasen:
1. Deterministische Flags (too_short, too_long, empty, no_heading, duplicate, boilerplate)
2. LLM-Judge (optional, per Ollama — bewertet flagged + Sample)
3. Synthese: aggregiert Flags + Verdicts zu Drop-Kandidaten-Liste
"""
from __future__ import annotations

import asyncio
import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

import ollama
import structlog

from halle_gehirn.config import Settings, get_settings
from halle_gehirn.pipeline.chunker import count_tokens

logger = structlog.get_logger(__name__)

# ────────────────────────── Schwellen ──────────────────────────

_MIN_HEALTHY_TOKENS = 64
_MAX_TOKENS = 768
_DUPLICATE_PREFIX_LEN = 200
_BOILERPLATE_THRESHOLD = 0.5
_BOILERPLATE_MIN_LINES = 3

# Boilerplate-Muster (Seitenzahlen, Copyright, Kopf-/Fusszeilen)
_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*-?\s*\d+\s*-?\s*$"),                    # Seitenzahl
    re.compile(r"^\s*seite\s+\d+", re.IGNORECASE),           # "Seite 12"
    re.compile(r"^\s*page\s+\d+", re.IGNORECASE),            # "Page 12"
    re.compile(r"copyright|©|\(c\)", re.IGNORECASE),          # Copyright
    re.compile(r"^\s*#{1,6}\s*$"),                            # Leere Headings
    re.compile(r"^_{3,}$|^-{3,}$|^\*{3,}$"),                 # Trennlinien
)


# ────────────────────────── Datentypen ──────────────────────────


@dataclass(frozen=True)
class ChunkFlag:
    """Eine Regelverletzung fuer einen Chunk."""

    chunk_index: int
    point_id: str
    datei: str
    rule: str
    detail: str


@dataclass(frozen=True)
class LLMVerdict:
    """LLM-Judge-Bewertung eines Chunks."""

    point_id: str
    datei: str
    chunk_index: int
    verdict: str   # "keep" | "drop" | "uncertain"
    reason: str
    score: float   # 0.0 – 1.0


@dataclass(frozen=True)
class DocSummary:
    """Zusammenfassung eines indexierten Dokuments."""

    datei: str
    titel: str
    chunk_count: int
    body_chunks: int
    table_chunks: int
    token_mean: float
    token_min: int
    token_max: int


@dataclass
class AuditReport:
    """Aggregierter Audit-Report."""

    doc_summaries: list[DocSummary] = field(default_factory=list)
    flags: list[ChunkFlag] = field(default_factory=list)
    verdicts: list[LLMVerdict] = field(default_factory=list)
    drop_candidates: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialisiert den Report als Dict (JSON-faehig)."""
        return {
            "doc_summaries": [asdict(s) for s in self.doc_summaries],
            "flags": [asdict(f) for f in self.flags],
            "verdicts": [asdict(v) for v in self.verdicts],
            "drop_candidates": self.drop_candidates,
        }


# ────────────────────────── Phase 0: Inventory ──────────────────────────


def build_doc_summary(
    datei: str, titel: str, chunks: list[dict[str, Any]],
) -> DocSummary:
    """Berechnet eine DocSummary aus rohen Qdrant-Chunk-Dicts."""
    payloads = [c.get("payload", {}) for c in chunks]
    texts = [p.get("text_raw", p.get("text", "")) for p in payloads]
    tokens = [count_tokens(t) for t in texts]
    table_count = sum(1 for p in payloads if p.get("table_ref"))
    body_count = len(chunks) - table_count
    return DocSummary(
        datei=datei,
        titel=titel,
        chunk_count=len(chunks),
        body_chunks=body_count,
        table_chunks=table_count,
        token_mean=round(sum(tokens) / len(tokens), 1) if tokens else 0.0,
        token_min=min(tokens) if tokens else 0,
        token_max=max(tokens) if tokens else 0,
    )


# ────────────────────────── Phase 1: Deterministische Flags ──────────────


def flag_chunks(chunks: list[dict[str, Any]], datei: str) -> list[ChunkFlag]:
    """Wendet deterministische Red-Flag-Regeln auf Chunks an.

    Args:
        chunks: Liste von Dicts mit ``point_id`` und ``payload``.
        datei: Dateiname des Dokuments (fuer Zuordnung).

    Returns:
        Liste von ChunkFlags (ein Chunk kann mehrere Flags haben).
    """
    flags: list[ChunkFlag] = []
    seen_prefixes: dict[str, list[int]] = defaultdict(list)

    for chunk in chunks:
        payload = chunk.get("payload", {})
        point_id = chunk.get("point_id", "")
        idx = payload.get("chunk_index", 0)
        text = payload.get("text_raw", payload.get("text", ""))
        is_table = bool(payload.get("table_ref"))

        # Regel: empty
        if not text.strip():
            flags.append(ChunkFlag(idx, point_id, datei, "empty", "Kein sichtbarer Text"))
            continue

        tk = count_tokens(text)

        # Regel: too_short (nur Body-Chunks)
        if not is_table and tk < _MIN_HEALTHY_TOKENS:
            flags.append(ChunkFlag(
                idx, point_id, datei, "too_short",
                f"{tk} Tokens (Schwelle {_MIN_HEALTHY_TOKENS})",
            ))

        # Regel: too_long
        if tk > _MAX_TOKENS:
            flags.append(ChunkFlag(
                idx, point_id, datei, "too_long",
                f"{tk} Tokens (Maximum {_MAX_TOKENS})",
            ))

        # Regel: no_heading (nur Body-Chunks)
        if not is_table:
            breadcrumb = payload.get("breadcrumb", "") or ""
            if not breadcrumb.strip():
                flags.append(ChunkFlag(
                    idx, point_id, datei, "no_heading",
                    "Kein Breadcrumb / Heading",
                ))

        # Regel: boilerplate
        if _is_boilerplate(text):
            flags.append(ChunkFlag(
                idx, point_id, datei, "boilerplate",
                "Ueberwiegend Boilerplate-Zeilen",
            ))

        # Duplikat-Erkennung vorbereiten
        prefix = _normalize_prefix(text)
        if prefix:
            seen_prefixes[prefix].append(idx)

    # Regel: duplicate_text (nach Durchlauf)
    for prefix, indices in seen_prefixes.items():
        if len(indices) > 1:
            for idx in indices:
                matching = [c for c in chunks if c["payload"].get("chunk_index") == idx]
                if matching:
                    pid = matching[0].get("point_id", "")
                    flags.append(ChunkFlag(
                        idx, pid, datei, "duplicate_text",
                        f"Dupliziert mit Chunks {indices}",
                    ))

    logger.info("flags_computed", datei=datei, flag_count=len(flags))
    return flags


def _normalize_prefix(text: str) -> str:
    """Normalisiert die ersten N Zeichen fuer Duplikat-Vergleich."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return normalized[:_DUPLICATE_PREFIX_LEN]


def _is_boilerplate(text: str) -> bool:
    """Prueft ob >50% der Zeilen Boilerplate-Muster matchen."""
    lines = [line for line in text.split("\n") if line.strip()]
    if len(lines) < _BOILERPLATE_MIN_LINES:
        return False
    bp_count = sum(
        1 for line in lines
        if any(p.search(line) for p in _BOILERPLATE_PATTERNS)
    )
    return bp_count / len(lines) > _BOILERPLATE_THRESHOLD


# ────────────────────────── Phase 2: LLM Judge ──────────────────────────

_JUDGE_PROMPT = """\
/no_think
Du bist ein Qualitaetspruefer fuer RAG-Chunks (Retrieval-Augmented Generation).

Bewerte den folgenden Chunk aus dem Dokument "{datei}":

<chunk>
{chunk_text}
</chunk>

Ist dieser Chunk nuetzlich fuer die semantische Suche in einer Wissensbasis?
Bewerte auf einer Skala von 0.0 (wertlos) bis 1.0 (hochwertig).

Antworte NUR mit einem JSON-Objekt (keine Erklaerung davor oder danach):
{{"verdict": "keep"|"drop"|"uncertain", "score": 0.0-1.0, "reason": "kurze Begruendung"}}"""


async def judge_chunks(
    chunks: list[dict[str, Any]],
    flagged_ids: set[str],
    datei: str,
    *,
    sample_pct: float = 0.1,
    settings: Settings | None = None,
) -> list[LLMVerdict]:
    """Bewertet Chunks per LLM-Judge (Ollama).

    Sendet alle geflaggten Chunks + ein zufaelliges Sample der
    nicht-geflaggten Chunks an das LLM.

    Args:
        chunks: Alle Chunks eines Dokuments.
        flagged_ids: Point-IDs der geflaggten Chunks.
        datei: Dateiname (fuer Prompt-Kontext).
        sample_pct: Anteil nicht-geflaggter Chunks als Sample.
        settings: Optionale Settings.

    Returns:
        Liste von LLMVerdicts.
    """
    s = settings or get_settings()
    client = ollama.AsyncClient(host=s.ollama_url)
    semaphore = asyncio.Semaphore(s.context_concurrency)

    # Chunks auswaehlen: flagged + random sample
    flagged = [c for c in chunks if c.get("point_id") in flagged_ids]
    non_flagged = [c for c in chunks if c.get("point_id") not in flagged_ids]
    sample_count = max(5, int(len(non_flagged) * sample_pct))
    sampled = random.sample(non_flagged, min(sample_count, len(non_flagged)))
    to_judge = flagged + sampled

    logger.info(
        "llm_judge_start",
        datei=datei,
        flagged=len(flagged),
        sampled=len(sampled),
        total=len(to_judge),
    )

    async def _judge_single(chunk: dict[str, Any]) -> LLMVerdict:
        payload = chunk.get("payload", {})
        text = payload.get("text_raw", payload.get("text", ""))[:1500]
        prompt = _JUDGE_PROMPT.format(datei=datei, chunk_text=text)
        async with semaphore:
            response = await client.chat(
                model=s.llm_model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.0, "num_predict": 256},
            )
        content: str = response["message"]["content"].strip()
        content = _strip_think_tags(content)
        return _parse_verdict(
            content,
            point_id=chunk.get("point_id", ""),
            datei=datei,
            chunk_index=payload.get("chunk_index", 0),
        )

    tasks = [_judge_single(c) for c in to_judge]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    verdicts: list[LLMVerdict] = []
    for chunk, result in zip(to_judge, results, strict=True):
        if isinstance(result, LLMVerdict):
            verdicts.append(result)
        elif isinstance(result, Exception):
            payload = chunk.get("payload", {})
            logger.debug(
                "llm_judge_failed",
                point_id=chunk.get("point_id", "")[:12],
                error=str(result),
            )
            verdicts.append(LLMVerdict(
                point_id=chunk.get("point_id", ""),
                datei=datei,
                chunk_index=payload.get("chunk_index", 0),
                verdict="uncertain",
                reason=f"LLM-Fehler: {result}",
                score=0.5,
            ))

    logger.info("llm_judge_done", datei=datei, verdicts=len(verdicts))
    return verdicts


def _parse_verdict(
    raw: str, point_id: str, datei: str, chunk_index: int,
) -> LLMVerdict:
    """Parst die LLM-Antwort als JSON-Verdict."""
    # JSON aus der Antwort extrahieren
    match = re.search(r"\{[^}]+\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            return LLMVerdict(
                point_id=point_id,
                datei=datei,
                chunk_index=chunk_index,
                verdict=str(data.get("verdict", "uncertain")),
                reason=str(data.get("reason", "")),
                score=float(data.get("score", 0.5)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return LLMVerdict(
        point_id=point_id,
        datei=datei,
        chunk_index=chunk_index,
        verdict="uncertain",
        reason=f"Parse-Fehler: {raw[:100]}",
        score=0.5,
    )


from halle_gehirn.llm_utils import strip_think_tags as _strip_think_tags  # noqa: E402


# ────────────────────────── Phase 3: Synthese ──────────────────────────


def synthesize(
    doc_summaries: list[DocSummary],
    flags: list[ChunkFlag],
    verdicts: list[LLMVerdict],
) -> AuditReport:
    """Aggregiert Flags und Verdicts zu einem AuditReport.

    Drop-Kandidaten:
    - LLM verdict == "drop" ODER score < 0.3
    - Mehrere kritische Flags (empty, too_short + no_heading)

    Args:
        doc_summaries: Inventar-Zusammenfassungen.
        flags: Alle deterministischen Flags.
        verdicts: Alle LLM-Verdicts (kann leer sein).

    Returns:
        AuditReport mit Drop-Kandidaten-Liste.
    """
    # Flags pro point_id gruppieren
    flags_by_pid: dict[str, list[ChunkFlag]] = defaultdict(list)
    for f in flags:
        flags_by_pid[f.point_id].append(f)

    drop_candidates: list[dict[str, Any]] = []
    seen_pids: set[str] = set()

    # LLM-basierte Drop-Kandidaten
    for v in verdicts:
        if v.verdict == "drop" or v.score < 0.3:
            drop_candidates.append({
                "point_id": v.point_id,
                "datei": v.datei,
                "chunk_index": v.chunk_index,
                "reason": f"LLM: {v.verdict} (score={v.score:.2f}) — {v.reason}",
            })
            seen_pids.add(v.point_id)

    # Flag-basierte Drop-Kandidaten
    for pid, chunk_flags in flags_by_pid.items():
        if pid in seen_pids:
            continue
        rules = {f.rule for f in chunk_flags}
        # Kritisch: empty
        if "empty" in rules:
            drop_candidates.append({
                "point_id": pid,
                "datei": chunk_flags[0].datei,
                "chunk_index": chunk_flags[0].chunk_index,
                "reason": "Flag: empty",
            })
            seen_pids.add(pid)
            continue
        # Kritisch: too_short + no_heading (doppeltes Signal)
        if "too_short" in rules and "no_heading" in rules:
            drop_candidates.append({
                "point_id": pid,
                "datei": chunk_flags[0].datei,
                "chunk_index": chunk_flags[0].chunk_index,
                "reason": "Flags: too_short + no_heading",
            })
            seen_pids.add(pid)

    report = AuditReport(
        doc_summaries=doc_summaries,
        flags=flags,
        verdicts=verdicts,
        drop_candidates=drop_candidates,
    )
    logger.info(
        "audit_synthesized",
        total_flags=len(flags),
        total_verdicts=len(verdicts),
        drop_candidates=len(drop_candidates),
    )
    return report
