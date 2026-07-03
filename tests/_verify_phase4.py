"""End-to-End-Verifikation Phase 4 (Retrieval).

Zeigt den vollstaendigen Retrieval-Pfad mit Vorher/Nachher-Vergleich:

1. Upsert Test-Chunks -> Qdrant (halle_wissen_test)
2. Router klassifiziert Query-Typ
3. Embed Query -> Hybrid Query -> MMR
4. Zeigt Treffer VOR dem Rerank (Hybrid-Scores)
5. Reranking via echte Ollama-Logprobs (Ja/Nein-Prompt)
6. Zeigt rohe LLM-Logprobs-Response eines Rerank-Calls
7. Zeigt Treffer NACH dem Rerank (rerank_scores)
8. Confidence-Gate Ampel
9. Cleanup

Voraussetzung: Qdrant + Ollama muessen laufen.

Aufruf:
    python tests/_verify_phase4.py
"""
from __future__ import annotations

import asyncio
import json
import math
import sys

import ollama
from qdrant_client import QdrantClient

# Patch settings BEFORE importing modules
_QDRANT_URL = "http://localhost:6335"
_TEST_COLLECTION = "halle_wissen_test"


def _test_settings():
    from halle_gehirn.config import Settings
    return Settings(
        ollama_url="http://localhost:11434",
        qdrant_url=_QDRANT_URL,
        qdrant_collection=_TEST_COLLECTION,
        embedding_dim=1024,
        top_k_initial=10,
        top_k_final=3,
        llm_model="qwen3:8b",
        use_mmr=True,
        mmr_lambda=0.7,
        rerank_num_predict=8,
        rerank_top_logprobs=5,
        use_router=True,
        use_query_transform=False,
    )


def _check_services():
    """Prueft ob Qdrant und Ollama erreichbar sind."""
    settings = _test_settings()
    try:
        c = QdrantClient(url=_QDRANT_URL, timeout=5)
        c.get_collections()
    except Exception:
        print("SKIP: Qdrant nicht erreichbar")
        sys.exit(0)
    try:
        oc = ollama.Client(host=settings.ollama_url)
        oc.list()
    except Exception:
        print(f"SKIP: Ollama nicht erreichbar ({settings.ollama_url})")
        sys.exit(0)
    print(f"[OK] Qdrant + Ollama erreichbar ({settings.ollama_url})\n")


def _setup_test_data(settings):
    """Erstellt Test-Collection mit 5 Chunks."""
    import halle_gehirn.vector_store.schema as schema_mod
    import halle_gehirn.vector_store.qdrant_client as client_mod

    # Monkey-patch
    schema_mod.get_settings = _test_settings
    client_mod.get_settings = _test_settings
    client_mod.get_qdrant_client.cache_clear()

    from halle_gehirn.vector_store.qdrant_client import (
        ensure_collection, upsert_chunks,
    )
    from halle_gehirn.vector_store.schema import (
        ChunkPayload, DocType, Bereich, Quelltyp, Herkunft, Thema,
    )

    client = QdrantClient(url=_QDRANT_URL, timeout=60)
    if client.collection_exists(_TEST_COLLECTION):
        client.delete_collection(_TEST_COLLECTION)

    ensure_collection(client)

    texts = [
        "Der UR10e ist ein kollaborativer Roboterarm mit 10 kg Nutzlast und 1300 mm Reichweite.",
        "Die Sicherheitszone um den Cobot muss mindestens 500 mm betragen.",
        "Das MES-System protokolliert alle Produktionsdaten in Echtzeit.",
        "Der Greifer des UR10e kann Werkstuecke bis 5 kg greifen.",
        "Die Modellfabrik der BTU Cottbus-Senftenberg dient der Lehre und Forschung.",
    ]

    payloads = []
    for i, text in enumerate(texts):
        payloads.append(ChunkPayload(
            text=text,
            text_raw=text,
            source_type="pdf",
            chunk_index=i,
            char_start=0,
            char_end=len(text),
            ingested_at="2024-01-01T00:00:00+00:00",
            source_hash="verify_phase4",
            titel="Testdokument Phase 4",
            doc_type=DocType.ANLAGENDOKU,
            bereich=[Bereich.INFRASTRUKTUR],
            quelltyp=Quelltyp.PRIMAER,
            herkunft=Herkunft.LEHRSTUHL_AT,
            thema=[Thema.MRK],
        ))

    # Embed mit echtem Ollama (expliziter Client auf settings.ollama_url)
    embed_client = ollama.Client(host=settings.ollama_url)
    print("[..] Embedding 5 Chunks...")
    result = embed_client.embed(
        model=settings.embedding_model,
        input=texts,
    )
    dense_vecs = [v[:settings.embedding_dim] for v in result["embeddings"]]

    from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder
    sparse_emb = FastEmbedSparseEmbedder(settings=settings)
    sparse_vecs = sparse_emb.embed(texts)

    total = upsert_chunks(payloads, dense_vecs, sparse_vecs, client=client)
    print(f"[OK] {total} Chunks upserted in {_TEST_COLLECTION}\n")
    return client


async def _run_retrieval(settings):
    """Fuehrt den Retrieval-Pfad aus mit Vorher/Nachher-Vergleich."""
    from halle_gehirn.retrieval.router import KeywordRouter
    from halle_gehirn.embeddings.reranker import LogprobsReranker, _extract_yes_prob
    from halle_gehirn.pipeline.stages.confidence import ConfidenceGate
    from halle_gehirn.vector_store.qdrant_client import hybrid_query

    query = "Welche Nutzlast hat der UR10e Roboterarm?"

    # -- 1. Router --
    router = KeywordRouter(settings=settings)
    query_type = router.route(query)
    print(f"{'='*70}")
    print(f"[1] ROUTER")
    print(f"    Query: '{query}'")
    print(f"    Typ:   {query_type}")

    # -- 2. Embed Query --
    embed_client = ollama.Client(host=settings.ollama_url)
    print(f"\n[2] EMBEDDING QUERY...")
    result = embed_client.embed(model=settings.embedding_model, input=[query])
    query_dense = result["embeddings"][0][:settings.embedding_dim]

    from halle_gehirn.embeddings.sparse_embedder import FastEmbedSparseEmbedder
    sparse_emb = FastEmbedSparseEmbedder(settings=settings)
    query_sparse = sparse_emb.embed([query])[0]

    # -- 3. Hybrid Query --
    hits = hybrid_query(
        query_dense=query_dense,
        query_sparse=query_sparse,
        limit=settings.top_k_initial,
    )

    # -- Vorher: Hybrid-Scores --
    print(f"\n[3] HYBRID QUERY: {len(hits)} Treffer")
    print(f"\n{'-'*70}")
    print(f" VOR RERANK (Hybrid/RRF-Scores)")
    print(f"{'-'*70}")
    for i, h in enumerate(hits):
        text = h.payload.get("text", "")[:65]
        print(f"  {i+1}. score={h.score:.4f}  | {text}")

    # Speichere Pre-Rerank-Reihenfolge
    pre_rerank = [(h.point_id, h.score, h.payload.get("text", "")[:50]) for h in hits]

    # -- 4. MMR --
    from halle_gehirn.retrieval.retriever import _mmr_reorder
    if settings.use_mmr and len(hits) > 1:
        hits = _mmr_reorder(hits, query_dense, lam=settings.mmr_lambda)
        print(f"\n[4] MMR: {len(hits)} Treffer (umgeordnet)")

    # -- 5. Einen rohen LLM-Rerank-Call zeigen --
    print(f"\n{'-'*70}")
    print(f" ROHE LLM-LOGPROBS-RESPONSE (1 Beispiel-Call)")
    print(f"{'-'*70}")

    # Manueller Einzel-Call fuer Transparenz
    first_hit = hits[0]
    first_text = first_hit.payload.get("text", "")[:2000]
    raw_prompt = (
        f"Ist das folgende Dokument relevant fuer die Frage?\n\n"
        f"Dokument:\n{first_text}\n\n"
        f"Frage: {query}\n\n"
        f"Antworte nur mit Ja oder Nein."
    )
    raw_client = ollama.Client(host=settings.ollama_url)
    raw_response = raw_client.chat(
        model=settings.llm_model,
        messages=[{"role": "user", "content": raw_prompt}],
        think=False,
        logprobs=True,
        top_logprobs=5,
        options={"temperature": 0.0, "num_predict": 8},
    )

    # Response anzeigen
    raw_content = raw_response.get("message", {}).get("content", "")
    raw_logprobs = raw_response.get("logprobs") or []
    print(f"  Prompt (gekuerzt): ...'{query}' -> Ja/Nein?")
    print(f"  Text-Antwort:      '{raw_content}'")
    print(f"  Logprobs vorhanden: {bool(raw_logprobs)}")
    if raw_logprobs:
        first_lp = raw_logprobs[0]
        print(f"  Erstes Token:      '{first_lp.get('token', '?')}'")
        print(f"  Logprob:           {first_lp.get('logprob', '?')}")
        print(f"  P(token):          {math.exp(first_lp.get('logprob', -99)):.6f}")
        print(f"  Top-Logprobs:")
        for alt in first_lp.get("top_logprobs", [])[:5]:
            t = alt.get("token", "?")
            lp = alt.get("logprob", -99)
            p = math.exp(lp)
            print(f"    '{t:12s}' logprob={lp:8.4f}  P={p:.6f}")

        extracted = _extract_yes_prob(raw_logprobs)
        print(f"  -> P(Ja) extrahiert: {extracted:.6f}")
    else:
        print("  WARNUNG: KEINE LOGPROBS -- Ollama-Version zu alt oder Modell unterstuetzt es nicht")
        print(f"  Rohe Response-Keys: {list(raw_response.keys())}")

    # -- 6. Vollstaendiger Rerank --
    print(f"\n[5] RERANKING via Ollama-Logprobs ({settings.llm_model})...")
    reranker = LogprobsReranker(settings=settings)
    hits = await reranker.rerank(query, hits)

    # -- Nachher: Rerank-Scores --
    print(f"\n{'-'*70}")
    print(f" NACH RERANK (Logprobs P(Ja)-Scores)")
    print(f"{'-'*70}")
    for i, h in enumerate(hits):
        text = h.payload.get("text", "")[:55]
        print(f"  {i+1}. rerank={h.rerank_score:.4f}  hybrid={h.score:.4f}  | {text}")

    # -- 7. Top-K Final --
    final = hits[:settings.top_k_final]
    print(f"\n[6] TOP-K FINAL: {len(final)} Treffer")

    # -- 8. Confidence Gate --
    gate = ConfidenceGate(settings=settings)
    level = gate.assess(final)
    top_score = final[0].rerank_score if final else 0.0
    print(f"\n{'-'*70}")
    print(f" CONFIDENCE-AMPEL")
    print(f"{'-'*70}")
    print(f"  Level:     {level.upper()}")
    print(f"  Top-Score: {top_score:.4f}")
    thresholds = f"gruen >= {settings.conf_green} | gelb >= {settings.conf_yellow} | rot < {settings.conf_yellow}"
    print(f"  Schwellen: {thresholds}")

    # -- Verifikation --
    print(f"\n{'='*70}")
    print(f" VERIFIKATION")
    print(f"{'='*70}")
    checks = []

    # Check 1: Reranker hat Scores > 0
    has_scores = all(h.rerank_score > 0 for h in final)
    checks.append(("rerank_scores > 0", has_scores))

    # Check 2: Scores unterscheiden sich (NICHT alle gleich)
    scores = [h.rerank_score for h in final]
    scores_differ = len(set(f"{s:.4f}" for s in scores)) > 1 if len(scores) > 1 else True
    checks.append(("scores unterscheiden sich", scores_differ))

    # Check 3: Top-Hit enthaelt UR10e
    top_text = final[0].payload.get("text", "") if final else ""
    has_ur10e = "UR10e" in top_text or "Nutzlast" in top_text
    checks.append(("top_hit relevant (UR10e/Nutzlast)", has_ur10e))

    # Check 4: Confidence nicht rot
    not_rot = level != "rot"
    checks.append(("confidence != rot", not_rot))

    # Check 5: Router-Typ korrekt
    is_factual = query_type == "factual"
    checks.append(("router=factual", is_factual))

    # Check 6: Logprobs vorhanden
    has_logprobs = bool(raw_logprobs)
    checks.append(("logprobs vorhanden", has_logprobs))

    for name, ok in checks:
        status = "OK" if ok else "FAIL"
        print(f"  [{status:4s}] {name}")

    all_ok = all(ok for _, ok in checks)
    print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    return all_ok


def _cleanup(client):
    """Raumt die Test-Collection auf."""
    if client.collection_exists(_TEST_COLLECTION):
        client.delete_collection(_TEST_COLLECTION)
    print(f"\n[OK] Cleanup: {_TEST_COLLECTION} geloescht")

    # Verify other collections untouched
    cols = {c.name for c in client.get_collections().collections}
    print(f"[OK] Verbleibende Collections: {cols}")


def main():
    settings = _test_settings()
    _check_services()

    # Patch settings globally
    import halle_gehirn.vector_store.schema as schema_mod
    import halle_gehirn.vector_store.qdrant_client as client_mod
    schema_mod.get_settings = _test_settings
    client_mod.get_settings = _test_settings
    client_mod.get_qdrant_client.cache_clear()

    client = _setup_test_data(settings)
    try:
        ok = asyncio.run(_run_retrieval(settings))
    finally:
        _cleanup(client)
        # Restore
        from halle_gehirn.config import get_settings
        schema_mod.get_settings = get_settings
        client_mod.get_settings = get_settings
        client_mod.get_qdrant_client.cache_clear()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
