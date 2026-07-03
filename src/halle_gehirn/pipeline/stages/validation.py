"""URL-Whitelist + Citation-Enforcement -- Phase 5.

Anti-Halluzination Stufe 2: Entfernt erfundene URLs und prueft
ob jede Aussage mit einer Quellen-ID [S1]/[S2] belegt ist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Regex fuer URLs und Citation-IDs
_URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
_CITATION_PATTERN = re.compile(r"\[S(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ValidationResult:
    """Ergebnis der Citation-Validierung."""

    cleaned_answer: str
    citations_found: list[str] = field(default_factory=list)
    citations_valid: list[str] = field(default_factory=list)
    citations_invalid: list[str] = field(default_factory=list)
    urls_removed: list[str] = field(default_factory=list)
    ungrounded_sentences: list[str] = field(default_factory=list)


class CitationValidator:
    """URL-Whitelist + Citation-Enforcement.

    Prueft und bereinigt die generierte Antwort:
    1. Entfernt URLs die nicht in den Quell-Payloads vorkommen
    2. Prueft ob Citation-IDs [S1] etc. gueltige Quellen referenzieren
    3. Markiert Saetze ohne Citation als unbelegt
    """

    def validate(
        self, answer: str, sources: list[Any],
    ) -> ValidationResult:
        """Validiert die Antwort gegen die Quellen.

        Args:
            answer: Die generierte Antwort.
            sources: RetrievalHit-Objekte (die Quellen).

        Returns:
            ValidationResult mit bereinigter Antwort und Report.
        """
        num_sources = len(sources)
        allowed_urls = _extract_source_urls(sources)

        # 1. URL-Whitelist
        cleaned, removed = _filter_urls(answer, allowed_urls)

        # 2. Citation-IDs pruefen
        found_ids = _CITATION_PATTERN.findall(cleaned)
        valid_ids: list[str] = []
        invalid_ids: list[str] = []
        for sid in found_ids:
            if 1 <= int(sid) <= num_sources:
                valid_ids.append(f"[S{sid}]")
            else:
                invalid_ids.append(f"[S{sid}]")

        # Ungueltige Citations entfernen
        for inv in invalid_ids:
            cleaned = cleaned.replace(inv, "")

        # 3. Unbelegte Saetze erkennen
        ungrounded = _find_ungrounded_sentences(cleaned)

        result = ValidationResult(
            cleaned_answer=cleaned.strip(),
            citations_found=[f"[S{s}]" for s in found_ids],
            citations_valid=valid_ids,
            citations_invalid=invalid_ids,
            urls_removed=removed,
            ungrounded_sentences=ungrounded,
        )

        logger.info(
            "validation_done",
            citations_valid=len(valid_ids),
            citations_invalid=len(invalid_ids),
            urls_removed=len(removed),
            ungrounded=len(ungrounded),
        )
        return result


def _extract_source_urls(sources: list[Any]) -> set[str]:
    """Extrahiert erlaubte URLs aus den Quell-Payloads."""
    urls: set[str] = set()
    for src in sources:
        payload = getattr(src, "payload", {}) or {}
        url = payload.get("source_url", "")
        if url:
            urls.add(url)
    return urls


def _filter_urls(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Entfernt URLs die nicht in der Whitelist sind.

    Returns:
        Tuple (bereinigter Text, Liste entfernter URLs).
    """
    removed: list[str] = []
    found_urls = _URL_PATTERN.findall(text)
    for url in found_urls:
        if not any(url.startswith(a) for a in allowed) and allowed:
            text = text.replace(url, "[URL entfernt]")
            removed.append(url)
    return text, removed


def _find_ungrounded_sentences(text: str) -> list[str]:
    """Findet Saetze ohne Citation-ID.

    Ignoriert kurze Saetze (< 20 Zeichen) und Meta-Saetze
    (Quellenverweise am Ende).
    """
    sentences = _SENTENCE_SPLIT.split(text)
    ungrounded: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:
            continue
        # Meta-Saetze ueberspringen (Quellenangaben)
        if sent.lower().startswith(("quelle", "verwendete quellen", "hinweis:")):
            continue
        if not _CITATION_PATTERN.search(sent):
            ungrounded.append(sent)
    return ungrounded
