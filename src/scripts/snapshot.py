"""Qdrant-Snapshot-Verwaltung fuer die konfigurierte Collection.

Usage:
    python -m scripts.snapshot create
    python -m scripts.snapshot list
"""
from __future__ import annotations

import argparse

import structlog

from halle_gehirn.observability.logging_config import configure_logging
from halle_gehirn.vector_store.qdrant_client import (
    create_snapshot,
    get_qdrant_client,
    list_snapshots,
)

logger = structlog.get_logger(__name__)


def main() -> None:
    """Haupteinstiegspunkt fuer das Snapshot-Script."""
    parser = argparse.ArgumentParser(
        description="Qdrant-Snapshot-Verwaltung fuer halle_wissen",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create", help="Neuen Snapshot erstellen")
    sub.add_parser("list", help="Vorhandene Snapshots auflisten")
    args = parser.parse_args()

    configure_logging(dev=True)
    _client = get_qdrant_client()

    if args.command == "create":
        name = create_snapshot()
        logger.info("snapshot_created_cli", name=name)
    elif args.command == "list":
        snaps = list_snapshots()
        if not snaps:
            logger.info("no_snapshots_found")
        for snap in snaps:
            logger.info("snapshot_entry", **snap)


if __name__ == "__main__":
    main()
