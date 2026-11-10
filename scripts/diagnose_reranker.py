"""Reranker-Diagnose: Rohe Logprobs fuer die Sensoren-Frage.

Fuehrt die Sensoren-Frage gegen Qdrant aus (Hybrid-Retrieval),
dann zeigt pro Top-K-Kandidat die rohen Logprobs:
  - first_token, logprob, P(Ja)
  - top_logprobs (alle Alternativen)

Ziel: Pruefen ob der Reranker differenziert (verschiedene P(Ja))
oder ob alle 1.0 sind (keine Differenzierung → Prompt schaerfen).

Usage:
    python scripts/diagnose_reranker.py
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ollama  # noqa: E402

from halle_gehirn.config import get_settings  # noqa: E402
from halle_gehirn.llm_utils import strip_think_tags  # noqa: E402

QUERY = "Welche Sensoren eignen sich fuer Predictive Maintenance?"

# The reranker prompt (must match reranker.py)
_RERANK_PROMPT = """\
Ist das folgende Dokument relevant fuer die Frage?

Dokument:
{document}

Frage: {query}

Antworte nur mit Ja oder Nein."""

_YES_TOKENS = frozenset({"Ja", "ja", "JA", "Yes", "yes", "YES"})


def _match_yes(token: str, logprob: float) -> float | None:
    """Check if token is affirmative, return P(Ja)."""
    if not token:
        return None
    if token in _YES_TOKENS:
        return math.exp(logprob)
    cleaned = token.strip(".,!?;: ").lower()
    if cleaned in ("ja", "yes"):
        return math.exp(logprob)
    return None


async def main() -> None:
    settings = get_settings()
    client = ollama.Client(host=settings.ollama_url)
    model = settings.llm_model

    print(f"Model: {model}")
    print(f"Ollama: {settings.ollama_url}")
    print(f"Query: {QUERY}")
    print()

    # 1. Retrieve top-K from Qdrant
    from halle_gehirn.pipeline.factory import build_query_pipeline  # noqa: E402

    pipeline = build_query_pipeline(settings)
    hits = await pipeline.retriever.retrieve(QUERY)
    print(f"Retrieved {len(hits)} hits from Qdrant")
    print("=" * 80)

    # 2. Score each hit with raw logprobs
    for i, hit in enumerate(hits[:10]):
        payload = getattr(hit, "payload", {}) or {}
        text = str(payload.get("text", ""))[:200]
        titel = payload.get("titel", "?")
        page = payload.get("page", "?")
        point_id = getattr(hit, "point_id", "?")

        prompt = _RERANK_PROMPT.format(
            document=str(payload.get("text", ""))[:2000],
            query=QUERY,
        )

        response = await asyncio.to_thread(
            client.chat,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            think=False,
            logprobs=True,
            top_logprobs=5,
            options={"temperature": 0.0, "num_predict": 8},
        )

        # Extract raw response
        raw_content = ""
        if isinstance(response, dict):
            raw_content = response.get("message", {}).get("content", "")
            logprobs_data = response.get("logprobs") or []
        else:
            raw_content = getattr(getattr(response, "message", None), "content", "")
            logprobs_data = getattr(response, "logprobs", None) or []

        cleaned_content = strip_think_tags(raw_content.strip())

        # Extract P(Ja)
        p_ja = 0.0
        first_token = "?"
        first_logprob = -999.0
        all_top = []

        for entry in logprobs_data:
            if isinstance(entry, dict):
                tok = entry.get("token", "").strip()
                lp = entry.get("logprob", -10.0)
                top = entry.get("top_logprobs", [])
            else:
                tok = getattr(entry, "token", "").strip()
                lp = getattr(entry, "logprob", -10.0)
                top = getattr(entry, "top_logprobs", None) or []

            if not tok:
                continue  # skip whitespace tokens

            first_token = tok
            first_logprob = lp

            # Check if first token itself is Ja
            match = _match_yes(tok, lp)
            if match is not None:
                p_ja = match

            # Collect all alternatives
            for alt in top:
                if isinstance(alt, dict):
                    at = alt.get("token", "").strip()
                    alp = alt.get("logprob", -10.0)
                else:
                    at = getattr(alt, "token", "").strip()
                    alp = getattr(alt, "logprob", -10.0)
                all_top.append((at, alp, math.exp(alp)))

                if p_ja == 0.0:
                    m = _match_yes(at, alp)
                    if m is not None:
                        p_ja = m

            break  # only first non-empty token

        print(f"\n--- Hit {i+1} | {point_id} ---")
        print(f"  Titel:  {titel}")
        print(f"  Seite:  {page}")
        print(f"  Text:   {text[:120]}...")
        print(f"  Raw:    {repr(raw_content[:80])}")
        print(f"  Clean:  {repr(cleaned_content[:80])}")
        print(f"  1st Token: {repr(first_token)}  logprob={first_logprob:.4f}  P={math.exp(first_logprob):.6f}")
        print(f"  P(Ja):  {p_ja:.6f}")
        if all_top:
            print("  Top logprobs:")
            for tok, lp, p in sorted(all_top, key=lambda x: -x[2]):
                marker = " ← Ja" if tok.strip(".,!?;: ").lower() in ("ja", "yes") else ""
                print(f"    {repr(tok):>12}  logprob={lp:>8.4f}  P={p:.6f}{marker}")

    print("\n" + "=" * 80)
    print("DONE. If all P(Ja) ≈ 1.0 → prompt needs sharpening.")
    print("If P(Ja) varies → reranker differentiates correctly.")


if __name__ == "__main__":
    asyncio.run(main())
