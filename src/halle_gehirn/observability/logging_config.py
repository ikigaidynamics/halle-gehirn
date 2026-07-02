"""structlog-Setup für Halle-Gehirn.

Konsolen-Renderer in der Entwicklung, JSON in Produktion. Alle Module holen
sich ihren Logger via `structlog.get_logger(__name__)` und loggen strukturiert
(`logger.info("event", key=value)`), niemals via `print` (Ausnahme: CLI-Output).
"""
from __future__ import annotations

import logging
import sys

import structlog

from halle_gehirn.config import get_settings


def configure_logging(*, dev: bool = True) -> None:
    """Konfiguriert structlog + stdlib-logging.

    Args:
        dev: True → farbiger Konsolen-Renderer; False → JSON-Zeilen (Produktion).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer()
        if dev
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
