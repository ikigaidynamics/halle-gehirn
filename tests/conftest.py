"""Gemeinsame Test-Fixtures fuer Halle-Gehirn."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

# Basis-Verzeichnisse
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEST_DATA_DIR = PROJECT_ROOT / "tests" / "data"

# tiktoken offline: zeigt TIKTOKEN_CACHE_DIR auf einen vorgewaermten
# repo-lokalen Cache (scripts/cache_tiktoken.py), falls vorhanden und
# nicht bereits explizit gesetzt. So laeuft die Test-Collection auch
# ohne Egress (CI/Offline-Runner), da der Chunker cl100k_base beim
# Import laedt. Kein Cache → normales tiktoken-Verhalten (Download).
_TIKTOKEN_CACHE = PROJECT_ROOT / ".tiktoken_cache"
if "TIKTOKEN_CACHE_DIR" not in os.environ and _TIKTOKEN_CACHE.is_dir():
    os.environ["TIKTOKEN_CACHE_DIR"] = str(_TIKTOKEN_CACHE)


@pytest.fixture
def test_data_dir() -> Path:
    """Liefert den Pfad zum Test-Daten-Verzeichnis."""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_DATA_DIR
