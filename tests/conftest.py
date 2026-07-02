"""Gemeinsame Test-Fixtures fuer Halle-Gehirn."""
from __future__ import annotations

from pathlib import Path

import pytest

# Basis-Verzeichnisse
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TEST_DATA_DIR = PROJECT_ROOT / "tests" / "data"


@pytest.fixture
def test_data_dir() -> Path:
    """Liefert den Pfad zum Test-Daten-Verzeichnis."""
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return TEST_DATA_DIR
