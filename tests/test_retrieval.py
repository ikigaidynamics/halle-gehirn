"""Tests fuer Phase 4 — Retrieval-Schicht.

Testet Reranker, Router, Confidence-Gate und Retriever-Orchestration.
Unit-Tests mocken LLM/Qdrant; Integration-Tests (markiert) brauchen
echtes Ollama + Qdrant.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from halle_gehirn.config import Settings
from halle_gehirn.embeddings.reranker import (
    LogprobsReranker,
    _extract_yes_prob,
    _parse_yes_no,
    _strip_think_tags,
)
from halle_gehirn.pipeline.stages.confidence import (
    GELB,
    GRUEN,
    ROT,
    ConfidenceGate,
    _best_score,
)
from halle_gehirn.retrieval.router import (
    DEFINITION,
    FACTUAL,
    OVERVIEW,
    TEMPORAL,
    VERGLEICH,
    KeywordRouter,
)

# ── Hilfs-Datenklassen ──


@dataclass
class FakeHit:
    """Simuliert einen RetrievalHit."""

    point_id: str = "abc123"
    score: float = 0.5
    payload: dict[str, Any] = field(default_factory=lambda: {
        "text": "Der UR10e ist ein kollaborativer Roboterarm.",
        "titel": "Testdokument",
    })
    rerank_score: float | None = None


def _test_settings(**overrides: Any) -> Settings:
    """Settings fuer Tests (kein .env, kleine Werte)."""
    defaults = {
        "qdrant_url": "http://localhost:6335",
        "qdrant_collection": "halle_wissen_test",
        "embedding_dim": 8,
        "top_k_initial": 10,
        "top_k_final": 3,
        "conf_green": 0.7,
        "conf_yellow": 0.4,
        "use_router": True,
        "use_mmr": True,
        "mmr_lambda": 0.7,
        "rerank_num_predict": 8,
        "rerank_top_logprobs": 5,
        "use_query_transform": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_logprobs_response(
    token: str, logprob: float,
    alternatives: list[tuple[str, float]] | None = None,
) -> dict[str, Any]:
    """Erzeugt eine Ollama-Response mit Logprobs.

    Args:
        token: Das generierte Token.
        logprob: Log-Wahrscheinlichkeit des Tokens.
        alternatives: Optionale Top-Logprobs [(token, logprob), ...].
    """
    top_logprobs = [{"token": token, "logprob": logprob, "bytes": []}]
    for alt_token, alt_lp in (alternatives or []):
        top_logprobs.append({
            "token": alt_token, "logprob": alt_lp, "bytes": [],
        })
    return {
        "message": {"content": token},
        "logprobs": [
            {
                "token": token,
                "logprob": logprob,
                "bytes": [],
                "top_logprobs": top_logprobs,
            },
        ],
    }


# ═══════════════════ Logprobs-Extraktion ═══════════════════


class TestExtractYesProb:
    """Tests fuer _extract_yes_prob (echte Logprobs-Auswertung)."""

    def test_ja_as_generated_token(self) -> None:
        """'Ja' als erstes Token → exp(logprob)."""
        data = [{"token": "Ja", "logprob": -0.1, "top_logprobs": [
            {"token": "Ja", "logprob": -0.1},
            {"token": "Nein", "logprob": -2.3},
        ]}]
        score = _extract_yes_prob(data)
        assert abs(score - math.exp(-0.1)) < 1e-6

    def test_nein_generated_ja_in_alternatives(self) -> None:
        """'Nein' generiert, aber 'Ja' in top_logprobs."""
        data = [{"token": "Nein", "logprob": -0.5, "top_logprobs": [
            {"token": "Nein", "logprob": -0.5},
            {"token": "Ja", "logprob": -1.8},
        ]}]
        score = _extract_yes_prob(data)
        assert abs(score - math.exp(-1.8)) < 1e-6

    def test_no_yes_token_found(self) -> None:
        """Weder Ja noch Yes in Logprobs → 0.0."""
        data = [{"token": "Relevant", "logprob": -0.3, "top_logprobs": [
            {"token": "Relevant", "logprob": -0.3},
            {"token": "Das", "logprob": -1.5},
        ]}]
        assert _extract_yes_prob(data) == 0.0

    def test_empty_logprobs(self) -> None:
        assert _extract_yes_prob([]) == 0.0

    def test_ja_with_whitespace(self) -> None:
        """Token ' Ja' mit fuehrendem Leerzeichen wird erkannt."""
        data = [{"token": " Ja", "logprob": -0.2, "top_logprobs": [
            {"token": " Ja", "logprob": -0.2},
        ]}]
        score = _extract_yes_prob(data)
        assert abs(score - math.exp(-0.2)) < 1e-6

    def test_yes_english_variant(self) -> None:
        """'Yes' wird ebenfalls erkannt."""
        data = [{"token": "Yes", "logprob": -0.05, "top_logprobs": [
            {"token": "Yes", "logprob": -0.05},
        ]}]
        score = _extract_yes_prob(data)
        assert abs(score - math.exp(-0.05)) < 1e-6

    def test_high_confidence_ja(self) -> None:
        """Hoher Logprob → Score nahe 1.0."""
        data = [{"token": "Ja", "logprob": -0.01, "top_logprobs": [
            {"token": "Ja", "logprob": -0.01},
        ]}]
        score = _extract_yes_prob(data)
        assert score > 0.98

    def test_low_confidence_ja(self) -> None:
        """Niedriger Logprob → Score nahe 0.0."""
        data = [{"token": "Nein", "logprob": -0.1, "top_logprobs": [
            {"token": "Nein", "logprob": -0.1},
            {"token": "Ja", "logprob": -5.0},
        ]}]
        score = _extract_yes_prob(data)
        assert score < 0.01


class TestParseYesNo:
    """Tests fuer den Text-Fallback _parse_yes_no."""

    def test_ja(self) -> None:
        assert _parse_yes_no("Ja") == 1.0

    def test_nein(self) -> None:
        assert _parse_yes_no("Nein") == 0.0

    def test_ja_with_dot(self) -> None:
        assert _parse_yes_no("Ja.") == 1.0

    def test_yes_english(self) -> None:
        assert _parse_yes_no("yes") == 1.0

    def test_garbage(self) -> None:
        assert _parse_yes_no("vielleicht") == 0.0

    def test_empty(self) -> None:
        assert _parse_yes_no("") == 0.0


class TestStripThinkTags:
    """Tests fuer qwen3 Think-Block-Bereinigung."""

    def test_no_think_block(self) -> None:
        assert _strip_think_tags("Ja") == "Ja"

    def test_think_then_answer(self) -> None:
        text = "<think>Lass mich ueberlegen...</think>Ja"
        assert _strip_think_tags(text) == "Ja"

    def test_think_with_whitespace(self) -> None:
        text = "<think>Denke...</think>\n  Nein  "
        assert _strip_think_tags(text) == "Nein"

    def test_only_think_block(self) -> None:
        text = "<think>Nur Denken, keine Antwort</think>"
        assert _strip_think_tags(text) == "Nur Denken, keine Antwort"

    def test_empty_after_think(self) -> None:
        text = "<think></think>"
        assert _strip_think_tags(text) == ""


class TestLogprobsReranker:
    """Tests fuer LogprobsReranker (gemockt)."""

    @pytest.mark.asyncio
    async def test_rerank_sorts_by_logprob_score(self) -> None:
        """Reranker sortiert Hits absteigend nach P(Ja)."""
        settings = _test_settings()
        reranker = LogprobsReranker(settings=settings)

        hits = [
            FakeHit(point_id="a", score=0.5, payload={"text": "Niedrig"}),
            FakeHit(point_id="b", score=0.8, payload={"text": "Hoch"}),
            FakeHit(point_id="c", score=0.6, payload={"text": "Mittel"}),
        ]

        # Mock: a=Nein(P(Ja)≈0.17), b=Ja(P(Ja)≈0.90), c=Ja(P(Ja)≈0.55)
        responses = iter([
            _make_logprobs_response("Nein", -0.5, [("Ja", -1.8)]),
            _make_logprobs_response("Ja", -0.1),
            _make_logprobs_response("Ja", -0.6),
        ])

        def mock_chat(**kwargs: Any) -> dict[str, Any]:
            return next(responses)

        reranker._client = MagicMock()
        reranker._client.chat = mock_chat

        result = await reranker.rerank("Testfrage", hits)
        assert result[0].point_id == "b"  # Hoechster P(Ja)
        assert result[0].rerank_score > 0.85
        assert result[1].point_id == "c"
        assert result[2].point_id == "a"
        assert result[2].rerank_score < 0.2

    @pytest.mark.asyncio
    async def test_rerank_empty_list(self) -> None:
        """Leere Liste bleibt leer."""
        settings = _test_settings()
        reranker = LogprobsReranker(settings=settings)
        result = await reranker.rerank("Frage", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_handles_llm_error(self) -> None:
        """Bei LLM-Fehler: Score 0.0, kein Crash."""
        settings = _test_settings()
        reranker = LogprobsReranker(settings=settings)
        hits = [FakeHit(point_id="a", payload={"text": "Text"})]

        def mock_chat_error(**kwargs: Any) -> dict[str, Any]:
            raise ConnectionError("Ollama nicht erreichbar")

        reranker._client = MagicMock()
        reranker._client.chat = mock_chat_error

        result = await reranker.rerank("Frage", hits)
        assert len(result) == 1
        assert result[0].rerank_score == 0.0

    @pytest.mark.asyncio
    async def test_rerank_fallback_without_logprobs(self) -> None:
        """Ohne Logprobs: Fallback auf Text-Parsing (Ja=1.0)."""
        settings = _test_settings()
        reranker = LogprobsReranker(settings=settings)
        hits = [FakeHit(point_id="a", payload={"text": "Text"})]

        def mock_chat(**kwargs: Any) -> dict[str, Any]:
            return {"message": {"content": "Ja"}, "logprobs": None}

        reranker._client = MagicMock()
        reranker._client.chat = mock_chat

        result = await reranker.rerank("Frage", hits)
        assert result[0].rerank_score == 1.0

    @pytest.mark.asyncio
    async def test_rerank_think_block_fallback(self) -> None:
        """Think-Block wird im Fallback-Pfad korrekt gestripped."""
        settings = _test_settings()
        reranker = LogprobsReranker(settings=settings)
        hits = [FakeHit(point_id="a", payload={"text": "Text"})]

        def mock_chat(**kwargs: Any) -> dict[str, Any]:
            return {
                "message": {"content": "<think>Hmm...</think>Ja"},
                "logprobs": None,
            }

        reranker._client = MagicMock()
        reranker._client.chat = mock_chat

        result = await reranker.rerank("Frage", hits)
        assert result[0].rerank_score == 1.0


# ═══════════════════ Router ═══════════════════


class TestKeywordRouter:
    """Tests fuer den Keyword-Router."""

    def test_factual_default(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Welche Nutzlast hat der UR10e?") == FACTUAL

    def test_vergleich(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Vergleich UR10e und UR5e") == VERGLEICH

    def test_definition_was_ist(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Was ist ein Cobot?") == DEFINITION

    def test_temporal_wann(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Wann wurde die Anlage installiert?") == TEMPORAL

    def test_temporal_year(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Projekte aus 2023") == TEMPORAL

    def test_overview(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        result = router.route("Gib mir einen Überblick über die Anlagen")
        assert result == OVERVIEW

    def test_definition_erklaere(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        result = router.route("Erkläre die Sicherheitszone")
        assert result == DEFINITION

    def test_router_disabled(self) -> None:
        """Bei use_router=False: immer FACTUAL."""
        settings = _test_settings(use_router=False)
        router = KeywordRouter(settings=settings)
        assert router.route("Vergleich X und Y") == FACTUAL

    def test_unterschied(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        result = router.route("Unterschied zwischen UR10e und UR5e")
        assert result == VERGLEICH

    def test_vorteil_nachteil(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        assert router.route("Vorteile des UR10e") == VERGLEICH

    def test_zusammenfassung(self) -> None:
        router = KeywordRouter(settings=_test_settings())
        result = router.route("Zusammenfassung der Ergebnisse")
        assert result == OVERVIEW


# ═══════════════════ Confidence Gate ═══════════════════


class TestConfidenceGate:
    """Tests fuer das Ampel-Confidence-Gate."""

    def test_gruen(self) -> None:
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(rerank_score=0.85)]
        assert gate.assess(hits) == GRUEN

    def test_gelb(self) -> None:
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(rerank_score=0.55)]
        assert gate.assess(hits) == GELB

    def test_rot(self) -> None:
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(rerank_score=0.2)]
        assert gate.assess(hits) == ROT

    def test_empty_list_rot(self) -> None:
        gate = ConfidenceGate(settings=_test_settings())
        assert gate.assess([]) == ROT

    def test_boundary_green(self) -> None:
        """Exakt CONF_GREEN => gruen."""
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(rerank_score=0.7)]
        assert gate.assess(hits) == GRUEN

    def test_boundary_yellow(self) -> None:
        """Exakt CONF_YELLOW => gelb."""
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(rerank_score=0.4)]
        assert gate.assess(hits) == GELB

    def test_uses_best_score(self) -> None:
        """Gate verwendet den hoechsten Score."""
        gate = ConfidenceGate(settings=_test_settings())
        hits = [
            FakeHit(rerank_score=0.3),
            FakeHit(rerank_score=0.8),
            FakeHit(rerank_score=0.5),
        ]
        assert gate.assess(hits) == GRUEN

    def test_fallback_to_score(self) -> None:
        """Ohne rerank_score: faellt auf score zurueck."""
        gate = ConfidenceGate(settings=_test_settings())
        hits = [FakeHit(score=0.75, rerank_score=None)]
        assert gate.assess(hits) == GRUEN

    def test_custom_thresholds(self) -> None:
        """Konfigurierbare Schwellen."""
        settings = _test_settings(conf_green=0.9, conf_yellow=0.6)
        gate = ConfidenceGate(settings=settings)
        hits = [FakeHit(rerank_score=0.75)]
        assert gate.assess(hits) == GELB


class TestBestScore:
    """Tests fuer _best_score Hilfsfunktion."""

    def test_prefers_rerank_score(self) -> None:
        hits = [FakeHit(score=0.3, rerank_score=0.9)]
        assert _best_score(hits) == 0.9

    def test_falls_back_to_score(self) -> None:
        hits = [FakeHit(score=0.6, rerank_score=None)]
        assert _best_score(hits) == 0.6

    def test_empty_list(self) -> None:
        assert _best_score([]) == 0.0


# ═══════════════════ MMR ═══════════════════


class TestMMR:
    """Tests fuer MMR-Diversifizierung."""

    def test_mmr_reorder_preserves_all_hits(self) -> None:
        from halle_gehirn.retrieval.retriever import _mmr_reorder

        hits = [
            FakeHit(point_id="a", score=0.9, payload={"text": "Roboter UR10e Arm"}),
            FakeHit(point_id="b", score=0.8, payload={"text": "Sicherheitszone Halle"}),
            FakeHit(point_id="c", score=0.7, payload={"text": "Roboter UR10e Greifer"}),
        ]
        result = _mmr_reorder(hits, [0.5] * 8, lam=0.7)
        assert len(result) == 3
        ids = {h.point_id for h in result}
        assert ids == {"a", "b", "c"}

    def test_mmr_single_hit(self) -> None:
        from halle_gehirn.retrieval.retriever import _mmr_reorder

        hits = [FakeHit(point_id="a", score=0.9)]
        result = _mmr_reorder(hits, [0.5] * 8)
        assert len(result) == 1

    def test_mmr_promotes_diversity(self) -> None:
        """MMR bevorzugt diverse Texte ueber aehnliche."""
        from halle_gehirn.retrieval.retriever import _mmr_reorder

        # a und c sind textlich fast identisch, b ist anders
        hits = [
            FakeHit(point_id="a", score=0.9, payload={
                "text": "Der UR10e Roboter hat sechs Achsen",
            }),
            FakeHit(point_id="b", score=0.85, payload={
                "text": "Sicherheitshinweise fuer die Halle beachten",
            }),
            FakeHit(point_id="c", score=0.88, payload={
                "text": "Der UR10e Roboter hat sechs Gelenke",
            }),
        ]
        result = _mmr_reorder(hits, [0.5] * 8, lam=0.5)
        # Bei lambda=0.5 sollte b (diverser) vor c kommen
        assert result[0].point_id == "a"  # Hoechster Score zuerst
        # b sollte wegen Diversitaet vor c liegen
        result_ids = [h.point_id for h in result]
        assert result_ids.index("b") < result_ids.index("c")


# ═══════════════════ Text-Jaccard ═══════════════════


class TestTextJaccard:
    """Tests fuer die Jaccard-Aehnlichkeit."""

    def test_identical_texts(self) -> None:
        from halle_gehirn.retrieval.retriever import _text_jaccard

        a = FakeHit(payload={"text": "hallo welt"})
        b = FakeHit(payload={"text": "hallo welt"})
        assert _text_jaccard(a, b) == 1.0

    def test_disjoint_texts(self) -> None:
        from halle_gehirn.retrieval.retriever import _text_jaccard

        a = FakeHit(payload={"text": "alpha beta"})
        b = FakeHit(payload={"text": "gamma delta"})
        assert _text_jaccard(a, b) == 0.0

    def test_partial_overlap(self) -> None:
        from halle_gehirn.retrieval.retriever import _text_jaccard

        a = FakeHit(payload={"text": "eins zwei drei"})
        b = FakeHit(payload={"text": "zwei drei vier"})
        sim = _text_jaccard(a, b)
        assert 0.0 < sim < 1.0
        # 2 gemeinsam / 4 union = 0.5
        assert abs(sim - 0.5) < 0.01

    def test_empty_text(self) -> None:
        from halle_gehirn.retrieval.retriever import _text_jaccard

        a = FakeHit(payload={"text": ""})
        b = FakeHit(payload={"text": "hallo"})
        assert _text_jaccard(a, b) == 0.0
