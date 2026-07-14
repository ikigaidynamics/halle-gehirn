"""Tests fuer WP7: Ops-Haertung.

- Rate-Limiter raeumt verwaiste IP-Buckets (Memory-Wachstum)
- Orchestrator-Session-Memory: LRU-Eviction bei _MAX_SESSIONS
- Admin-Key-Vergleich bleibt funktional (konstantzeit via
  secrets.compare_digest — Verhalten identisch, deckt test_api ab)
"""
from __future__ import annotations

from halle_gehirn.api.main import RateLimitMiddleware
from halle_gehirn.pipeline.orchestrator import QueryOrchestrator
from tests.test_orchestrator import _mock_pipeline


class TestRateLimiterSweep:
    """Verwaiste IP-Buckets werden entfernt."""

    def test_sweep_removes_stale_buckets(self) -> None:
        """Buckets ohne Anfragen im 60s-Fenster fliegen raus."""
        mw = RateLimitMiddleware(app=None, rpm=60)
        now = 1000.0
        mw._requests["alte-ip"] = [now - 120.0]  # ausserhalb Fenster
        mw._requests["leere-ip"] = []
        mw._requests["aktive-ip"] = [now - 10.0]

        mw._sweep(now)

        assert "alte-ip" not in mw._requests
        assert "leere-ip" not in mw._requests
        assert "aktive-ip" in mw._requests

    def test_sweep_updates_timestamp(self) -> None:
        """_sweep setzt den Zeitstempel fuer das naechste Intervall."""
        mw = RateLimitMiddleware(app=None, rpm=60)
        mw._sweep(5000.0)
        assert mw._last_sweep == 5000.0


class TestSessionLruEviction:
    """Session-Memory haelt maximal _MAX_SESSIONS Eintraege."""

    def test_oldest_session_evicted(self) -> None:
        """Bei Ueberlauf fliegt die am laengsten unbenutzte Session."""
        orch = QueryOrchestrator(_mock_pipeline())
        limit = QueryOrchestrator._MAX_SESSIONS
        for i in range(limit):
            orch._get_memory(f"s{i}")
        assert len(orch._sessions) == limit

        orch._get_memory("neu")
        assert len(orch._sessions) == limit
        assert "s0" not in orch._sessions  # aelteste evicted
        assert "neu" in orch._sessions

    def test_access_refreshes_lru_position(self) -> None:
        """Zugriff schuetzt eine Session vor der Eviction."""
        orch = QueryOrchestrator(_mock_pipeline())
        limit = QueryOrchestrator._MAX_SESSIONS
        for i in range(limit):
            orch._get_memory(f"s{i}")

        orch._get_memory("s0")  # s0 auffrischen
        orch._get_memory("neu")  # verdraengt jetzt s1, nicht s0

        assert "s0" in orch._sessions
        assert "s1" not in orch._sessions

    def test_same_session_returns_same_memory(self) -> None:
        """Wiederholter Zugriff liefert dieselbe Memory-Instanz."""
        orch = QueryOrchestrator(_mock_pipeline())
        m1 = orch._get_memory("abc")
        m2 = orch._get_memory("abc")
        assert m1 is m2
