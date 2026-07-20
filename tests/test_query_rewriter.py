"""Tests fuer Query-Rewriter (konversationelle Umschreibung).

Prueft die zweistufige Bypass-Logik, FAIL-OPEN-Semantik,
Ellipse-Erkennung und Orchestrator-Integration.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from halle_gehirn.config import Settings
from halle_gehirn.retrieval.query_rewriter import (
    QueryRewriter,
    RewriteResult,
    _needs_rewrite,
)


def _test_settings(**overrides: Any) -> Settings:
    """Settings fuer Tests (keine externen Dienste)."""
    defaults: dict[str, Any] = {
        "qdrant_url": "http://localhost:6335",
        "qdrant_collection": "test",
        "ollama_url": "http://localhost:11434",
        "use_query_rewrite": True,
    }
    defaults.update(overrides)
    return Settings(**defaults)


_HISTORY = [
    {"role": "user", "content": "Welche Anlagen gibt es in der Modellfabrik?"},
    {"role": "assistant", "content": "Es gibt den UR10e, die CP Factory..."},
]


# ═══════════════════ Bypass-Logik ═══════════════════


class TestNeedsRewrite:
    """Tests fuer _needs_rewrite (zweistufiger Bypass)."""

    def test_no_history_always_bypass(self) -> None:
        """Erster Turn: immer Bypass, egal was in der Query steht."""
        assert _needs_rewrite("Was kann er?", []) is False
        assert _needs_rewrite("Und die Nutzlast?", []) is False

    def test_pronoun_with_history(self) -> None:
        """Pronomen mit History → Rewrite."""
        assert _needs_rewrite("Was kann er?", _HISTORY) is True
        assert _needs_rewrite("Gilt das auch dafuer?", _HISTORY) is True
        assert _needs_rewrite("Welche davon ist besser?", _HISTORY) is True

    def test_ellipse_start_with_history(self) -> None:
        """Ellipse-Anfang mit History → Rewrite."""
        assert _needs_rewrite("Und die Nutzlast?", _HISTORY) is True
        assert _needs_rewrite("Auch beim Greifroboter?", _HISTORY) is True
        assert _needs_rewrite("Was ist mit der CP Factory?", _HISTORY) is True

    def test_ellipse_words_with_history(self) -> None:
        """Ellipse-Woerter mit History → Rewrite."""
        assert _needs_rewrite("Die zweite Anlage?", _HISTORY) is True
        assert _needs_rewrite("Die andere auch?", _HISTORY) is True
        assert _needs_rewrite("Ebenfalls fuer den UR5e?", _HISTORY) is True

    def test_short_query_with_history(self) -> None:
        """Kurze Frage (<6 Woerter) mit History → Rewrite."""
        assert _needs_rewrite("Nutzlast?", _HISTORY) is True
        assert _needs_rewrite("Und der UR5e?", _HISTORY) is True

    def test_long_standalone_query_with_history(self) -> None:
        """Lange eigenstaendige Frage ohne Signalwoerter → kein Rewrite."""
        query = (
            "Wie funktioniert die automatische Kalibrierung"
            " beim Einrichten von Werkzeugen an der CP Factory?"
        )
        assert _needs_rewrite(query, _HISTORY) is False


# ═══════════════════ Rewrite-Aufruf ═══════════════════


class TestRewriteCall:
    """Tests fuer den LLM-Rewrite-Pfad."""

    @pytest.mark.asyncio
    async def test_successful_rewrite(self) -> None:
        """Erfolgreicher Rewrite loest Pronomen auf."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {
                "content": "Welche Nutzlast hat der UR10e Roboterarm?",
            },
        }

        result = await rewriter.rewrite("Was kann der?", _HISTORY)

        assert result.was_rewritten is True
        assert result.rewritten == "Welche Nutzlast hat der UR10e Roboterarm?"
        assert result.original == "Was kann der?"

    @pytest.mark.asyncio
    async def test_bypass_no_history(self) -> None:
        """Erster Turn ohne History: kein LLM-Call."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()

        result = await rewriter.rewrite(
            "Welche Anlagen gibt es in der Modellfabrik?", [],
        )

        assert result.was_rewritten is False
        assert result.rewritten == result.original
        rewriter._client.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_ellipse_without_pronoun_triggers_rewrite(self) -> None:
        """'Und die Nutzlast?' ohne Pronomen wird rewritten."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {
                "content": "Welche Nutzlast hat der UR10e?",
            },
        }

        result = await rewriter.rewrite("Und die Nutzlast?", _HISTORY)

        assert result.was_rewritten is True
        rewriter._client.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_fachbegriff_preserved(self) -> None:
        """Fachbegriffe bleiben exakt erhalten im Rewrite."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {
                "content": "Welche OPC UA Schnittstelle hat die CP Factory?",
            },
        }

        result = await rewriter.rewrite("Welche davon?", _HISTORY)

        assert "CP Factory" in result.rewritten
        assert "OPC UA" in result.rewritten


# ═══════════════════ FAIL-OPEN ═══════════════════


class TestFailOpen:
    """Tests fuer die FAIL-OPEN-Semantik."""

    @pytest.mark.asyncio
    async def test_llm_error_returns_original(self) -> None:
        """Bei LLM-Fehler: Original zurueck, kein Crash."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.side_effect = ConnectionError("Timeout")

        result = await rewriter.rewrite("Was kann der?", _HISTORY)

        assert result.was_rewritten is False
        assert result.rewritten == "Was kann der?"

    @pytest.mark.asyncio
    async def test_empty_result_returns_original(self) -> None:
        """Leere LLM-Antwort: Original zurueck."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {"content": ""},
        }

        result = await rewriter.rewrite("Was kann der?", _HISTORY)

        assert result.was_rewritten is False
        assert result.rewritten == "Was kann der?"

    @pytest.mark.asyncio
    async def test_too_long_result_returns_original(self) -> None:
        """Absurd langer Rewrite (>3x Original): Original zurueck."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {"content": "X " * 1000},
        }

        result = await rewriter.rewrite("Was kann der?", _HISTORY)

        assert result.was_rewritten is False
        assert result.rewritten == "Was kann der?"

    @pytest.mark.asyncio
    async def test_think_block_stripped(self) -> None:
        """Think-Block wird entfernt, Antwort danach verwendet."""
        rewriter = QueryRewriter(settings=_test_settings())
        rewriter._client = MagicMock()
        rewriter._client.chat.return_value = {
            "message": {
                "content": "<think>hmm...</think>Was hat der UR10e?",
            },
        }

        result = await rewriter.rewrite("Was kann der?", _HISTORY)

        assert result.rewritten == "Was hat der UR10e?"
        assert result.was_rewritten is True


# ═══════════════════ Orchestrator-Integration ═══════════════════


class TestOrchestratorIntegration:
    """Tests fuer die Integration im Orchestrator."""

    @pytest.mark.asyncio
    async def test_rewritten_query_goes_to_router(self) -> None:
        """Rewritten Query geht an Router, nicht das Original."""
        from halle_gehirn.pipeline.factory import QueryPipeline
        from halle_gehirn.pipeline.orchestrator import QueryOrchestrator
        from halle_gehirn.pipeline.stages.guardrails import GuardrailResult
        from halle_gehirn.pipeline.stages.validation import ValidationResult
        from tests.test_orchestrator import FakeHit

        s = _test_settings()
        p = MagicMock(spec=QueryPipeline)
        p.settings = s
        p.guardrail = MagicMock()
        p.guardrail.check_input.return_value = GuardrailResult(approved=True)
        p.guardrail.check_output.return_value = GuardrailResult(approved=True)
        p.guardrail.redact_pii.side_effect = lambda t: t
        p.router = MagicMock()
        p.router.route.return_value = "factual"
        p.query_rewriter = AsyncMock()
        p.query_rewriter.rewrite.return_value = RewriteResult(
            original="Was kann der?",
            rewritten="Was kann der UR10e Roboterarm?",
            was_rewritten=True,
        )
        p.query_transformer = AsyncMock()
        p.query_transformer.transform.return_value = [
            "Was kann der UR10e Roboterarm?",
        ]
        p.retriever = AsyncMock()
        p.retriever.retrieve.return_value = [FakeHit()]
        p.confidence_gate = MagicMock()
        p.confidence_gate.assess.return_value = "gruen"
        p.generator = AsyncMock()
        p.generator.generate_full.return_value = "Antwort [S1]."
        p.validator = MagicMock()
        p.validator.validate.return_value = ValidationResult(
            cleaned_answer="Antwort [S1].",
        )
        p.grounding_checker = AsyncMock()
        p.audit_logger = MagicMock()
        p.retrieval_logger = MagicMock()

        orch = QueryOrchestrator(p)
        await orch.run("Was kann der?", session_id="s1")

        # Router erhaelt rewritten query
        p.router.route.assert_called_with("Was kann der UR10e Roboterarm?")
        # Transform erhaelt rewritten query
        p.query_transformer.transform.assert_called_with(
            "Was kann der UR10e Roboterarm?",
        )
        # Generator erhaelt ORIGINAL query
        call_kwargs = p.generator.generate_full.call_args
        assert call_kwargs.kwargs["query"] == "Was kann der?"

    @pytest.mark.asyncio
    async def test_disabled_rewrite_passes_original(self) -> None:
        """use_query_rewrite=False: kein Rewrite-Call."""
        from halle_gehirn.pipeline.factory import QueryPipeline
        from halle_gehirn.pipeline.orchestrator import QueryOrchestrator
        from halle_gehirn.pipeline.stages.guardrails import GuardrailResult
        from halle_gehirn.pipeline.stages.validation import ValidationResult
        from tests.test_orchestrator import FakeHit

        s = _test_settings(use_query_rewrite=False)
        p = MagicMock(spec=QueryPipeline)
        p.settings = s
        p.guardrail = MagicMock()
        p.guardrail.check_input.return_value = GuardrailResult(approved=True)
        p.guardrail.check_output.return_value = GuardrailResult(approved=True)
        p.guardrail.redact_pii.side_effect = lambda t: t
        p.router = MagicMock()
        p.router.route.return_value = "factual"
        p.query_rewriter = AsyncMock()
        p.query_transformer = AsyncMock()
        p.query_transformer.transform.return_value = ["Testfrage"]
        p.retriever = AsyncMock()
        p.retriever.retrieve.return_value = [FakeHit()]
        p.confidence_gate = MagicMock()
        p.confidence_gate.assess.return_value = "gruen"
        p.generator = AsyncMock()
        p.generator.generate_full.return_value = "Antwort [S1]."
        p.validator = MagicMock()
        p.validator.validate.return_value = ValidationResult(
            cleaned_answer="Antwort [S1].",
        )
        p.grounding_checker = AsyncMock()
        p.audit_logger = MagicMock()
        p.retrieval_logger = MagicMock()

        orch = QueryOrchestrator(p)
        await orch.run("Testfrage", session_id="s1")

        # Rewriter wird NICHT aufgerufen
        p.query_rewriter.rewrite.assert_not_called()
