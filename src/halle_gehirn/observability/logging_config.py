"""structlog-Setup für Halle-Gehirn.

Konsolen-Renderer in der Entwicklung, JSON in Produktion. Alle Module holen
sich ihren Logger via `structlog.get_logger(__name__)` und loggen strukturiert
(`logger.info("event", key=value)`), niemals via `print` (Ausnahme: CLI-Output).
"""
from __future__ import annotations

import io
import logging
import sys

import structlog

from halle_gehirn.config import get_settings


def _ensure_utf8_streams() -> io.TextIOWrapper:
    """Stellt sicher, dass stdout und stderr UTF-8 verwenden (Windows-Fix).

    Unter Windows nutzen sys.stdout/sys.stderr standardmaessig cp1252,
    was bei Unicode-Zeichen aus PDF-Extrakten (Formeln, Sonderzeichen)
    zu ``'charmap' codec can't encode`` Fehlern fuehrt.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return sys.stdout


def configure_logging(*, dev: bool = True) -> None:
    """Konfiguriert structlog + stdlib-logging.

    Args:
        dev: True → farbiger Konsolen-Renderer; False → JSON-Zeilen (Produktion).
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    stream = _ensure_utf8_streams()
    logging.basicConfig(format="%(message)s", stream=stream, level=level)

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
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )
