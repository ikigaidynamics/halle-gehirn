"""Audit-Log (append-only, DSGVO) -- Phase 6.

Strukturierter Audit-Logger fuer alle Query-Pipeline-Durchlaeufe.
Schreibt append-only via structlog (JSON in Produktion).
Erfasst: Query-Hash, Quellen-IDs, Konfidenz, Latenz.
Kein File-I/O -- structlog-Renderer uebernimmt Output-Routing.
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger("halle_gehirn.audit")


class StructlogAuditLogger:
    """Append-only Audit-Logger via structlog.

    Schreibt jeden Pipeline-Durchlauf als strukturiertes Log-Event.
    In Produktion (JSON-Renderer) ergibt sich automatisch ein
    maschinenlesbares Audit-Trail.

    Erfuellt das ``AuditLogger``-Protocol aus ``protocols.py``.
    """

    def log(self, record: dict[str, Any]) -> None:
        """Schreibt einen Audit-Eintrag.

        Args:
            record: Dict mit Audit-Feldern (query_hash, confidence,
                    source_ids, latency_ms, etc.).
        """
        logger.info("audit_entry", **record)
