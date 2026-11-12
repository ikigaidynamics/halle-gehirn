"""Einstiegspunkt fuer das PyInstaller-Bundle (``halle-gehirn.exe``).

Aufgaben in genau dieser Reihenfolge (vor dem App-Import!):
1. CWD auf den Bundle-Root setzen (Ordner der EXE) — damit ``.env``,
   ``data/``, ``logs/`` und ``static/`` relativ gefunden werden.
2. Offline-Caches verdrahten: ``TIKTOKEN_CACHE_DIR`` (cl100k_base) und
   ``FASTEMBED_CACHE_PATH`` (BM25-Modell) zeigen in den Bundle-Ordner.
3. Uvicorn mit der FastAPI-App starten.

Der Import von ``halle_gehirn.api.main`` erfolgt bewusst SPAET, weil
``config.py`` beim Import die ``.env`` aus dem CWD liest.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def bundle_root() -> Path:
    """Verzeichnis der EXE (= Bundle-Root mit .env, data/, static/)."""
    return Path(sys.executable).resolve().parent


def prepare_environment() -> None:
    """Setzt CWD und Cache-Umgebungsvariablen fuer den Bundle-Betrieb."""
    root = bundle_root()
    os.chdir(root)

    caches = root / "caches"
    tiktoken_dir = caches / "tiktoken"
    fastembed_dir = caches / "fastembed"
    for d in (tiktoken_dir, fastembed_dir):
        d.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(tiktoken_dir))
    os.environ.setdefault("DATA_GYM_CACHE_DIR", str(tiktoken_dir))
    os.environ.setdefault("FASTEMBED_CACHE_PATH", str(fastembed_dir))

    _prime_tiktoken_registry()


def _prime_tiktoken_registry() -> None:
    """Befuellt die tiktoken-Encoding-Registry direkt aus dem Plugin-Modul.

    Im Gefrierbetrieb schlaegt tiktokens pkgutil-Scan des Namespace-Pakets
    ``tiktoken_ext`` fehl ("Unknown encoding cl100k_base"). Das Plugin-Modul
    ``tiktoken_ext.openai_public`` ist per hiddenimports im Bundle enthalten
    und wird hier als ENCODING_CONSTRUCTORS gesetzt.
    """
    import tiktoken.registry as registry
    from tiktoken_ext import openai_public

    if registry.ENCODING_CONSTRUCTORS is None:
        registry.ENCODING_CONSTRUCTORS = dict(
            openai_public.ENCODING_CONSTRUCTORS
        )


def main() -> None:
    """Startet die uvicorn-Server-Instanz der Halle-Gehirn-API."""
    prepare_environment()

    import uvicorn

    # Import nach prepare_environment: config.py liest .env aus dem CWD.
    from halle_gehirn.api.main import app
    from halle_gehirn.config import get_settings

    settings = get_settings()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
