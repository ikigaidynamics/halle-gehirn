"""Waermt den tiktoken-``cl100k_base``-Encoding-Cache offline vor.

Der Chunker laedt beim Import ``tiktoken.get_encoding("cl100k_base")`` —
das zieht die BPE-Datei einmalig aus dem Netz. In gesperrten Umgebungen
(CI ohne Egress, Offline-Runner) schlaegt das schon bei der Test-
Collection fehl. Dieses Skript legt die Datei unter ``.tiktoken_cache/``
ab; ``tests/conftest.py`` zeigt ``TIKTOKEN_CACHE_DIR`` dann dorthin.

Aufruf (einmalig, z.B. im CI-Setup vor pytest)::

    python scripts/cache_tiktoken.py

Idempotent: existiert die Datei bereits, passiert nichts.
"""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

# Original-Quelle (von tiktoken erwartet) — der Cache-Dateiname ist der
# SHA1-Hex dieser URL.
_BLOB_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
)
# Netz-erreichbarer Spiegel (GitHub raw) fuer gesperrte Blob-Hosts.
_MIRROR_URL = (
    "https://raw.githubusercontent.com/pkoukk/tiktoken-go-loader/"
    "main/assets/cl100k_base.tiktoken"
)
_EXPECTED_MIN_BYTES = 1_000_000

CACHE_DIR = Path(__file__).resolve().parent.parent / ".tiktoken_cache"


def _cache_key(url: str) -> str:
    """tiktoken-Cache-Dateiname = SHA1-Hex der Original-URL."""
    return hashlib.sha1(url.encode()).hexdigest()


def warm_cache(cache_dir: Path = CACHE_DIR) -> Path:
    """Legt die cl100k_base-Datei im Cache ab (idempotent).

    Returns:
        Pfad zur Cache-Datei.

    Raises:
        RuntimeError: Download fehlgeschlagen oder Datei zu klein.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / _cache_key(_BLOB_URL)
    if target.exists() and target.stat().st_size >= _EXPECTED_MIN_BYTES:
        print(f"tiktoken-Cache bereits vorhanden: {target}")
        return target

    last_err: Exception | None = None
    for url in (_BLOB_URL, _MIRROR_URL):
        try:
            print(f"Lade cl100k_base von {url} …")
            with urllib.request.urlopen(url, timeout=60) as resp:
                data = resp.read()
            if len(data) < _EXPECTED_MIN_BYTES:
                raise RuntimeError(f"Datei zu klein ({len(data)} Bytes)")
            target.write_bytes(data)
            print(f"Gespeichert: {target} ({len(data)} Bytes)")
            return target
        except Exception as exc:
            print(f"  fehlgeschlagen: {exc}")
            last_err = exc

    raise RuntimeError(
        f"tiktoken-Cache konnte nicht erstellt werden: {last_err}"
    )


def main() -> int:
    """Waermt den Cache und verifiziert den Offline-Load."""
    import os

    target = warm_cache()
    os.environ["TIKTOKEN_CACHE_DIR"] = str(target.parent)
    import tiktoken

    enc = tiktoken.get_encoding("cl100k_base")
    assert enc.n_vocab == 100277, f"unerwartetes Vokabular: {enc.n_vocab}"
    print(f"Offline-Load OK (n_vocab={enc.n_vocab}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
