"""Phase 5 End-to-End Verification: Retrieve -> Generate gegen echtes Ollama + Qdrant.

Testet:
1. Gestreamte Antwort mit Source-IDs fuer UR10e-Frage
2. Refusal bei out-of-corpus Frage
3. Grounding-Check mit echtem LLM-Aufruf
"""
from __future__ import annotations

import asyncio
import os
import sys
import re

# Override config BEFORE any halle_gehirn import
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("LLM_MODEL", "qwen3:8b")

from halle_gehirn.config import Settings, get_settings  # noqa: E402
from halle_gehirn.retrieval.retriever import HybridRetriever  # noqa: E402
from halle_gehirn.generator.ollama_client import OllamaGenerator  # noqa: E402
from halle_gehirn.pipeline.stages.confidence import ConfidenceGate  # noqa: E402
from halle_gehirn.pipeline.stages.grounding import FaithfulnessChecker  # noqa: E402


SEPARATOR = "=" * 70


async def test_streamed_answer() -> str:
    """Test 1: Gestreamte Antwort mit Source-IDs."""
    print(f"\n{SEPARATOR}")
    print("TEST 1: GESTREAMTE ANTWORT — 'Welche Nutzlast hat der UR10e Roboterarm?'")
    print(SEPARATOR)

    settings = get_settings()
    print(f"  OLLAMA_URL:   {settings.ollama_url}")
    print(f"  LLM_MODEL:    {settings.llm_model}")
    print(f"  num_predict:  {settings.gen_num_predict}")
    print(f"  temperature:  {settings.gen_temperature}")
    print(f"  streaming:    {settings.streaming}")

    query = "Welche Nutzlast hat der UR10e Roboterarm?"

    # 1. Retrieve
    print(f"\n--- RETRIEVAL ---")
    retriever = HybridRetriever(settings=settings)
    hits = await retriever.retrieve(query)
    print(f"  Hits: {len(hits)}")
    for i, hit in enumerate(hits):
        titel = hit.payload.get("titel", "?")
        text_preview = hit.payload.get("text", "")[:100]
        print(f"  [S{i+1}] titel={titel}, score={hit.score:.4f}, "
              f"rerank={hit.rerank_score:.4f}")
        print(f"        text: {text_preview}...")

    # 2. Confidence Gate
    print(f"\n--- CONFIDENCE GATE ---")
    gate = ConfidenceGate(settings=settings)
    confidence = gate.assess(hits)
    print(f"  Ampel: {confidence}")

    # 3. Generate (streaming)
    print(f"\n--- GENERATION (streaming) ---")
    print(f"  think:       AN (Default qwen3 — think-Block wird gefiltert)")
    print(f"  num_predict: {settings.gen_num_predict}")
    generator = OllamaGenerator(settings=settings)

    full_answer = ""
    token_count = 0
    think_content_leaked = False

    print(f"\n  >>> Gestreamte Tokens:")
    print(f"  ", end="")
    async for token in generator.generate(query, hits, confidence=confidence):
        full_answer += token
        token_count += 1
        print(token, end="", flush=True)
        # Check for think-Block leak
        if "<think>" in token or "</think>" in token:
            think_content_leaked = True

    print(f"\n\n  >>> Stream Ende ({token_count} Token-Chunks)")

    # 4. Verify
    print(f"\n--- VERIFIKATION ---")
    has_source_ids = bool(re.search(r"\[S\d+\]", full_answer))
    answer_not_empty = len(full_answer.strip()) > 20
    no_think_leak = not think_content_leaked and "<think>" not in full_answer

    print(f"  Antwort leer?          {'NEIN' if answer_not_empty else 'JA — FEHLER!'}")
    print(f"  Quellen-IDs [Sn]?      {'JA' if has_source_ids else 'NEIN — FEHLER!'}")
    print(f"  <think>-Leak?          {'NEIN (korrekt)' if no_think_leak else 'JA — FEHLER!'}")
    print(f"  num_predict verwendet: {settings.gen_num_predict} (>= 1024: "
          f"{'OK' if settings.gen_num_predict >= 1024 else 'ZU KLEIN'})")
    print(f"  Antwort-Laenge:        {len(full_answer)} Zeichen")

    if not all([answer_not_empty, has_source_ids, no_think_leak]):
        print(f"\n  *** TEST 1: FEHLGESCHLAGEN ***")
    else:
        print(f"\n  *** TEST 1: BESTANDEN ***")

    return full_answer


async def test_refusal() -> None:
    """Test 2: Refusal bei out-of-corpus Frage."""
    print(f"\n{SEPARATOR}")
    print("TEST 2: REFUSAL — 'Wie hoch ist der Jahresumsatz von Siemens?'")
    print(SEPARATOR)

    settings = get_settings()
    query = "Wie hoch ist der Jahresumsatz von Siemens?"

    # 1. Retrieve
    print(f"\n--- RETRIEVAL ---")
    retriever = HybridRetriever(settings=settings)
    hits = await retriever.retrieve(query)
    print(f"  Hits: {len(hits)}")
    for i, hit in enumerate(hits):
        titel = hit.payload.get("titel", "?")
        print(f"  [S{i+1}] titel={titel}, score={hit.score:.4f}, "
              f"rerank={hit.rerank_score:.4f}")

    # 2. Confidence Gate
    print(f"\n--- CONFIDENCE GATE ---")
    gate = ConfidenceGate(settings=settings)
    confidence = gate.assess(hits)
    print(f"  Ampel: {confidence}")

    # 3. Generate
    print(f"\n--- GENERATION ---")
    generator = OllamaGenerator(settings=settings)

    full_answer = ""
    async for token in generator.generate(query, hits, confidence=confidence):
        full_answer += token

    print(f"  Antwort:\n  {full_answer}")

    # 4. Verify
    print(f"\n--- VERIFIKATION ---")
    is_refusal = (
        confidence == "rot"
        or "keine" in full_answer.lower()
        or "nicht" in full_answer.lower()
        or "liegen mir" in full_answer.lower()
        or "belege" in full_answer.lower()
    )
    no_hallucination = "milliarden" not in full_answer.lower() and "mrd" not in full_answer.lower()

    print(f"  Confidence:       {confidence}")
    print(f"  Verweigert?       {'JA (korrekt)' if is_refusal else 'NEIN — FEHLER!'}")
    print(f"  Keine Erfindung?  {'JA (korrekt)' if no_hallucination else 'NEIN — HALLUZINATION!'}")

    if is_refusal and no_hallucination:
        print(f"\n  *** TEST 2: BESTANDEN ***")
    else:
        print(f"\n  *** TEST 2: FEHLGESCHLAGEN ***")


async def test_grounding() -> None:
    """Test 3: Grounding-Check mit echtem LLM-Aufruf."""
    print(f"\n{SEPARATOR}")
    print("TEST 3: GROUNDING-CHECK")
    print(SEPARATOR)

    settings = get_settings()

    # Erst: Code-Audit
    print(f"\n--- CODE-AUDIT grounding.py ---")
    import inspect
    from halle_gehirn.pipeline.stages import grounding as grounding_mod
    source = inspect.getsource(grounding_mod.FaithfulnessChecker._check_sentence)

    uses_think_false = "think=False" in source
    uses_no_think = "/no_think" in inspect.getsource(grounding_mod)
    except_returns_false = "return False" in source and "fail-safe" in source

    print(f"  think=False im LLM-Call?   {'JA (korrekt)' if uses_think_false else 'NEIN — FEHLER!'}")
    print(f"  /no_think im Prompt?       {'JA (korrekt)' if uses_no_think else 'NEIN'}")
    print(f"  except -> return False?    {'JA (fail-safe, korrekt)' if except_returns_false else 'NEIN -- GEFAHR!'}")

    # Echten Grounding-Check ausfuehren
    print(f"\n--- ECHTER GROUNDING-LAUF ---")
    retriever = HybridRetriever(settings=settings)
    query = "Welche Nutzlast hat der UR10e Roboterarm?"
    hits = await retriever.retrieve(query)

    # Simuliere eine korrekte Antwort
    correct_answer = (
        "Der UR10e Roboterarm hat eine Nutzlast von 12,5 kg [S1]. "
        "Er verfuegt ueber sechs Freiheitsgrade und eine Reichweite "
        "von 1300 mm [S1]. Der Roboter unterstuetzt sichere "
        "Mensch-Roboter-Kollaboration nach ISO/TS 15066 [S1]."
    )

    checker = FaithfulnessChecker(settings=settings)
    result = await checker.check(correct_answer, hits)

    print(f"  Antwort geprueft:  '{correct_answer[:80]}...'")
    print(f"  grounded:          {result.grounded}")
    print(f"  score:             {result.score:.3f}")
    print(f"  total_sentences:   {result.total_sentences}")
    print(f"  grounded_sent:     {result.grounded_sentences}")
    print(f"  flagged_sent:      {result.flagged_sentences}")

    # Auch pruefen ob der LLM wirklich antwortet (nicht leer)
    import ollama as ollama_lib
    client = ollama_lib.Client(host=settings.ollama_url)
    test_prompt = (
        "/no_think\nKontext: Der UR10e hat eine Nutzlast von 12,5 kg.\n\n"
        "Satz: Der UR10e hat eine Nutzlast von 12,5 kg.\n\n"
        "Ist dieser Satz vollstaendig durch den Kontext gestuetzt? "
        "Antworte NUR mit Ja oder Nein."
    )
    raw_response = client.chat(
        model=settings.llm_model,
        messages=[{"role": "user", "content": test_prompt}],
        think=False,
        options={"temperature": 0.0, "num_predict": 8},
    )
    raw_content = raw_response["message"]["content"].strip()
    print(f"\n  Raw LLM-Antwort (Ja/Nein-Check): '{raw_content}'")
    print(f"  Antwort nicht leer?  {'JA (korrekt)' if raw_content else 'NEIN — LEER!'}")
    print(f"  Startet mit Ja?     {'JA' if raw_content.lower().startswith('ja') else 'NEIN'}")

    if result.total_sentences > 0 and result.score > 0 and raw_content:
        print(f"\n  *** TEST 3: BESTANDEN ***")
    else:
        print(f"\n  *** TEST 3: FEHLGESCHLAGEN ***")


async def main() -> None:
    """Fuehrt alle Phase-5-Verifikationstests aus."""
    print(SEPARATOR)
    print("PHASE 5 — END-TO-END VERIFIKATION")
    print(f"Ollama: {os.environ.get('OLLAMA_URL', 'default')}")
    print(f"Model:  {os.environ.get('LLM_MODEL', 'default')}")
    print(SEPARATOR)

    answer = await test_streamed_answer()
    await test_refusal()
    await test_grounding()

    print(f"\n{SEPARATOR}")
    print("ALLE TESTS ABGESCHLOSSEN")
    print(SEPARATOR)


if __name__ == "__main__":
    asyncio.run(main())
