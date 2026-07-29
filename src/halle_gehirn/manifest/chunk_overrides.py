"""Persistenter Override-Store fuer deaktivierte Chunks.

Speichert Chunk-IDs, die vom Retrieval ausgeschlossen werden sollen,
in ``data/chunk_overrides.yaml``. Die Overrides ueberstehen Re-Ingests,
weil ``upsert_chunks()`` die IDs vor dem Upsert prueft und das
``disabled``-Flag in den Qdrant-Payload injiziert.

Format::

    disabled:
      <chunk_id>:
        datei: abschlussarbeiten/thesis.pdf
        chunk_index: 5
        updated_at: "2026-07-29T14:00:00"
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

_DATA_DIR = Path("data")
_OVERRIDES_PATH = _DATA_DIR / "chunk_overrides.yaml"


def _load_raw(path: Path | None = None) -> dict[str, Any]:
    """Laedt die YAML-Datei als dict (oder leeres dict)."""
    p = path or _OVERRIDES_PATH
    if not p.exists():
        return {}
    raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def load_disabled_ids(path: Path | None = None) -> set[str]:
    """Liefert alle deaktivierten Chunk-IDs als Set (O(1) Lookup)."""
    raw = _load_raw(path)
    disabled = raw.get("disabled")
    if not isinstance(disabled, dict):
        return set()
    return set(disabled.keys())


def is_chunk_disabled(
    chunk_id: str, path: Path | None = None,
) -> bool:
    """Prueft, ob ein Chunk deaktiviert ist."""
    return chunk_id in load_disabled_ids(path)


def set_chunk_disabled(
    chunk_id: str,
    datei: str,
    chunk_index: int,
    disabled: bool,
    path: Path | None = None,
) -> None:
    """Setzt oder entfernt ein Override fuer einen Chunk.

    Args:
        chunk_id: Deterministische Chunk-ID (32-Zeichen Hex).
        datei: Dokumentpfad (fuer Lesbarkeit im YAML).
        chunk_index: Chunk-Index im Dokument.
        disabled: True = deaktivieren, False = reaktivieren.
        path: Optionaler Pfad (fuer Tests).
    """
    p = path or _OVERRIDES_PATH
    raw = _load_raw(p)
    if "disabled" not in raw or not isinstance(raw["disabled"], dict):
        raw["disabled"] = {}

    if disabled:
        raw["disabled"][chunk_id] = {
            "datei": datei,
            "chunk_index": chunk_index,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }
        logger.info(
            "chunk_disabled",
            chunk_id=chunk_id[:12],
            datei=datei,
            chunk_index=chunk_index,
        )
    else:
        removed = raw["disabled"].pop(chunk_id, None)
        if removed:
            logger.info(
                "chunk_enabled",
                chunk_id=chunk_id[:12],
                datei=datei,
                chunk_index=chunk_index,
            )

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
