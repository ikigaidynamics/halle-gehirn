"""Phase-5-Live-Verifikation gegen echtes Ollama + Qdrant.

Prueft den vollen Retrieve->Generate-Pfad:
1. Gestreamte Antwort (Think-Filterung, num_predict, Quellen-IDs)
2. Refusal bei unbelegter Frage
3. Grounding-Check mit echter LLM-Antwort

Verwendet OLLAMA_URL / LLM_MODEL aus .env bzw. Env-Overrides.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

# Projekt-Root setzen, damit .env und Imports funktionieren
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

# UTF-8 Ausgabe erzwingen (Windows cp1252 Problem)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def separator(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}\n")


async def main() -> None:
    # ── 0. Config laden & Connectivity pruefen ──
    separator("0. KONFIGURATION & CONNECTIVITY")

    from halle_gehirn.config import get_settings
    settings = get_settings()

    print(f"OLLAMA_URL:       {settings.ollama_url}")
    print(f"LLM_MODEL:        {settings.llm_model}")
    print(f"EMBEDDING_MODEL:  {settings.embedding_model}")
    print(f"QDRANT_URL:       {settings.qdrant_url}")
    print(f"QDRANT_COLLECTION:{settings.qdrant_collection}")
    print(f"GEN_NUM_PREDICT:  {settings.gen_num_predict}")
    print(f"GEN_TEMPERATURE:  {settings.gen_temperature}")
    print(f"USE_GROUNDING:    {settings.use_grounding_check}")
    print(f"GROUNDING_THRESH: {settings.grounding_threshold}")
    print(f"STREAMING:        {settings.streaming}")

    # Ollama-Erreichbarkeit
    import ollama
    client = ollama.Client(host=settings.ollama_url)
    try:
        version_info = client.list()
        model_names = [m.get("name", m.get("model", "?")) for m in version_info.get("models", [])]
        print(f"\nOllama erreichbar ({settings.ollama_url})")
        print(f"  Modelle: {model_names[:10]}")
        has_llm = any(settings.llm_model in m for m in model_names)
        has_emb = any(settings.embedding_model in m for m in model_names)
        print(f"  LLM '{settings.llm_model}' vorhanden: {has_llm}")
        print(f"  Embedding '{settings.embedding_model}' vorhanden: {has_emb}")
        if not has_llm:
            print(f"  FEHLER: {settings.llm_model} nicht verfuegbar!")
            sys.exit(1)
        if not has_emb:
            print(f"  FEHLER: {settings.embedding_model} nicht verfuegbar!")
            sys.exit(1)
    except Exception as e:
        print(f"FEHLER: Ollama nicht erreichbar: {e}")
        sys.exit(1)

    # Qdrant-Erreichbarkeit
    from qdrant_client import QdrantClient
    qclient = QdrantClient(url=settings.qdrant_url, timeout=10,
                           check_compatibility=False)
    try:
        info = qclient.get_collection(settings.qdrant_collection)
        print(f"\nQdrant erreichbar. Collection '{settings.qdrant_collection}': "
              f"{info.points_count} Punkte, Status={info.status}")
        if info.points_count == 0:
            print("FEHLER: Collection leer! Bitte zuerst reindex ausfuehren.")
            sys.exit(1)
    except Exception as e:
        print(f"FEHLER: Qdrant nicht erreichbar: {e}")
        sys.exit(1)

    # ── 1. GESTREAMTE ANTWORT ──
    separator("1. GESTREAMTE ANTWORT: 'Welche Nutzlast hat der UR10e Roboterarm?'")

    query_nutzlast = "Welche Nutzlast hat der UR10e Roboterarm?"

    # 1a. Retrieval
    print("--- Retrieval ---")
    from halle_gehirn.retrieval.retriever import HybridRetriever
    retriever = HybridRetriever(settings=settings)
    hits = await retriever.retrieve(query_nutzlast)

    print(f"Treffer: {len(hits)}")
    for i, hit in enumerate(hits):
        titel = hit.payload.get("titel", "?")
        text_preview = hit.payload.get("text", "")[:120].replace("\n", " ")
        print(f"  [{i+1}] score={hit.score:.4f} rerank={hit.rerank_score:.4f} "
              f"titel='{titel}'")
        print(f"       text='{text_preview}...'")

    if not hits:
        print("FEHLER: Keine Treffer! Retrieval fehlgeschlagen.")
        sys.exit(1)

    # 1b. Confidence
    from halle_gehirn.pipeline.stages.confidence import ConfidenceGate
    gate = ConfidenceGate(settings=settings)
    confidence = gate.assess(hits)
    print(f"\nConfidence: {confidence} "
          f"(top rerank_score={hits[0].rerank_score:.4f})")

    # 1c. Nachweis: qwen3 think-Block existiert bei Default-Call
    print("\n--- Raw Ollama-Call (Nachweis: think-Block wird erzeugt) ---")
    raw_response = client.chat(
        model=settings.llm_model,
        messages=[
            {"role": "user", "content": "Was ist 2+2? Antworte kurz."},
        ],
        options={"num_predict": 256, "temperature": 0.0},
    )
    raw_content = raw_response["message"]["content"]
    has_think = "<think>" in raw_content
    print(f"Raw-Antwort enthaelt <think>-Block: {has_think}")
    if has_think:
        think_end = raw_content.find("</think>")
        if think_end > 0:
            think_content = raw_content[raw_content.find("<think>")+7:think_end]
            print(f"Think-Inhalt (erste 200 Zeichen): "
                  f"'{think_content[:200].strip()}'")
            after_think = raw_content[think_end+8:].strip()
            print(f"Sichtbare Antwort nach </think>: '{after_think}'")
    else:
        print(f"Raw-Antwort (kein think): '{raw_content[:300]}'")

    # 1d. Streaming-Generierung
    print("\n--- Streaming-Generierung ---")
    print(f"  num_predict = {settings.gen_num_predict}")
    print(f"  temperature = {settings.gen_temperature}")
    print(f"  think-Modus: AN (clientseitig per State-Machine gefiltert)")
    print(f"  Ollama-Chat-Aufruf: KEIN think=False (Reasoning erwuenscht)")
    print()

    from halle_gehirn.generator.ollama_client import OllamaGenerator
    generator = OllamaGenerator(settings=settings)

    print(">>> TOKEN-STREAM BEGINNT >>>")
    full_answer = ""
    token_count = 0
    think_leaked = False
    t_start = time.time()

    async for token in generator.generate(
        query=query_nutzlast,
        hits=hits,
        confidence=confidence,
    ):
        token_count += 1
        full_answer += token
        # Echtzeit-Ausgabe der Tokens
        sys.stdout.write(token)
        sys.stdout.flush()
        # Pruefe auf Think-Leak
        if "<think>" in token or "</think>" in token:
            think_leaked = True

    t_elapsed = time.time() - t_start
    print("\n<<< TOKEN-STREAM ENDE <<<")

    print(f"\n--- Stream-Statistik ---")
    print(f"  Tokens empfangen:    {token_count}")
    print(f"  Antwort-Laenge:      {len(full_answer)} Zeichen")
    print(f"  Dauer:               {t_elapsed:.1f}s")
    print(f"  <think>-Leak:        "
          f"{'JA - FEHLER!' if think_leaked else 'NEIN (korrekt gefiltert)'}")
    print(f"  Antwort leer:        "
          f"{'JA - FEHLER!' if not full_answer.strip() else 'NEIN (OK)'}")

    # Quellen-IDs pruefen
    import re
    source_ids = re.findall(r"\[S\d+\]", full_answer)
    unique_ids = sorted(set(source_ids))
    print(f"  Quellen-IDs gefunden: {unique_ids} "
          f"(gesamt {len(source_ids)} Referenzen)")
    if source_ids:
        print("  PASS: Antwort enthaelt Quellen-IDs")
    else:
        print("  FAIL: Keine Quellen-IDs [S1]/[S2] in der Antwort!")

    print(f"\n--- Vollstaendige Antwort ---")
    print(full_answer)

    # ── 2. REFUSAL-TEST ──
    separator("2. REFUSAL: 'Wie hoch ist der Jahresumsatz von Siemens?'")

    query_refusal = "Wie hoch ist der Jahresumsatz von Siemens?"

    print("--- Retrieval ---")
    hits_refusal = await retriever.retrieve(query_refusal)
    print(f"Treffer: {len(hits_refusal)}")
    for i, hit in enumerate(hits_refusal):
        titel = hit.payload.get("titel", "?")
        print(f"  [{i+1}] score={hit.score:.4f} rerank={hit.rerank_score:.4f} "
              f"titel='{titel}'")

    confidence_refusal = gate.assess(hits_refusal)
    print(f"Confidence: {confidence_refusal}")

    print("\n--- Generierung (erwartet: Refusal oder Verweigerung) ---")
    refusal_answer = ""
    async for token in generator.generate(
        query=query_refusal,
        hits=hits_refusal,
        confidence=confidence_refusal,
    ):
        refusal_answer += token
        sys.stdout.write(token)
        sys.stdout.flush()

    print()

    # Pruefen ob Refusal
    refusal_markers = [
        "keine ausreichend",
        "liegen mir",
        "keine Belege",
        "nicht beantworten",
        "keine passenden",
        "unbelegte",
        "keine Informationen",
        "nicht oder nur teilweise",
        "b-tu.de",
        "keine ausreichenden",
        "keine Angaben",
        "Dazu liegen",
    ]
    is_refusal = any(m.lower() in refusal_answer.lower() for m in refusal_markers)
    print(f"\nRefusal erkannt: "
          f"{'JA (korrekt)' if is_refusal else 'NEIN'}")
    print(f"Confidence war: '{confidence_refusal}'")

    if confidence_refusal == "rot":
        print("Confidence-Gate hat korrekt auf ROT geschaltet -> "
              "Refusal-Template ausgeliefert.")
    elif is_refusal:
        print("LLM hat eigenstaendig verweigert (via System-Prompt-Regeln).")
    else:
        print("WARNUNG: Weder Confidence-Gate noch LLM haben verweigert!")
        print("Bei nur 3 Chunks im Korpus (alle UR10e) ist das problematisch.")
        print("Moegliche Ursache: Reranker gibt auch bei irrelevanten Fragen")
        print("hohe Scores, weil die Chunks die einzigen Kandidaten sind.")

    # ── 3. GROUNDING-CHECK ──
    separator("3. GROUNDING-CHECK (echte LLM-Antworten)")

    from halle_gehirn.pipeline.stages.grounding import (
        FaithfulnessChecker,
        _extract_sentences,
        _format_context,
        _GROUNDING_PROMPT,
    )

    checker = FaithfulnessChecker(settings=settings)

    # 3a. Positiver Sentence-Check
    print("--- Positiver Grounding-Check ---")
    test_sentence = "Der UR10e hat eine Nutzlast von 12,5 kg."
    context_text = _format_context(hits)

    prompt_pos = _GROUNDING_PROMPT.format(
        context=context_text[:3000],
        sentence=test_sentence,
    )
    print(f"Satz: '{test_sentence}'")
    print(f"Prompt (erste 300 Zeichen):\n  {prompt_pos[:300]}...\n")

    grounding_response = client.chat(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt_pos}],
        think=False,
        options={"temperature": 0.0, "num_predict": 8},
    )
    grounding_content = grounding_response["message"]["content"].strip()
    print(f"Rohe Grounding-Antwort: '{grounding_content}'")
    print(f"Beginnt mit 'Ja': {grounding_content.lower().startswith('ja')}")
    print(f"Antwort leer: {len(grounding_content) == 0}")

    if len(grounding_content) == 0:
        print("\nFEHLER: Leere Antwort! Das ist die qwen3-Falle:")
        print("  think=False + /no_think verwirrt das Modell.")
        print("  Im except-Block: return True -> Schutz aus!")

    # 3b. Negativer Sentence-Check
    print("\n--- Negativer Grounding-Check (erfundener Satz) ---")
    fake_sentence = "Der UR10e hat einen Preis von 45.000 Euro."
    prompt_neg = _GROUNDING_PROMPT.format(
        context=context_text[:3000],
        sentence=fake_sentence,
    )
    grounding_neg = client.chat(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt_neg}],
        think=False,
        options={"temperature": 0.0, "num_predict": 8},
    )
    grounding_neg_content = grounding_neg["message"]["content"].strip()
    print(f"Satz: '{fake_sentence}'")
    print(f"Grounding-Antwort: '{grounding_neg_content}'")
    print(f"Beginnt mit 'Nein': "
          f"{grounding_neg_content.lower().startswith('nein')}")

    # 3c. Voller Grounding-Check auf die generierte UR10e-Antwort
    print("\n--- Voller Grounding-Check auf die UR10e-Antwort ---")
    sentences = _extract_sentences(full_answer)
    print(f"Extrahierte Saetze: {len(sentences)}")
    for s in sentences:
        print(f"  - '{s[:100]}{'...' if len(s)>100 else ''}'")

    grounding_result = await checker.check(full_answer, hits)
    print(f"\nGrounding-Ergebnis:")
    print(f"  grounded:            {grounding_result.grounded}")
    print(f"  score:               {grounding_result.score:.3f}")
    print(f"  total_sentences:     {grounding_result.total_sentences}")
    print(f"  grounded_sentences:  {grounding_result.grounded_sentences}")
    if grounding_result.flagged_sentences:
        print(f"  flagged_sentences:")
        for fs in grounding_result.flagged_sentences:
            print(f"    - '{fs[:100]}'")
    else:
        print(f"  flagged_sentences:   (keine)")

    # ── 4. GROUNDING EXCEPT-DEFAULT ANALYSE ──
    separator("4. GROUNDING EXCEPT-DEFAULT ANALYSE")

    print("grounding.py Zeile 136-138:")
    print("  except Exception as exc:")
    print("      logger.warning('grounding_sentence_failed', error=str(exc))")
    print("      return True  # Bei Fehler: nicht flaggen")
    print()
    print("PROBLEM: Ein abgestuerzter Anti-Halluzinations-Check darf NICHT")
    print("alles durchwinken. 'return True' bei Fehler heisst:")
    print("  -> Wenn Ollama down ist -> alle Saetze 'grounded' -> Schutz aus")
    print("  -> Wenn leere Antwort + Exception -> alles OK")
    print()
    print("EMPFEHLUNG: 'return False' (Fail-Closed / strenger Default).")
    print("Begruendung: Ein Sicherheits-Check der bei Fehler 'alles OK'")
    print("meldet, ist schlimmer als keiner. Fail-Closed ist Standard bei")
    print("Anti-Halluzinations-Checks.")
    print()
    print("Think-Mode im Grounding-Check:")
    print(f"  grounding.py: think=False   (korrekt)")
    print(f"  Prompt: /no_think prefix    (korrekt)")
    print(f"  num_predict=8               (korrekt)")
    print(f"  -> Korrekt konfiguriert gegen qwen3-Falle")

    # ── ZUSAMMENFASSUNG ──
    separator("ZUSAMMENFASSUNG")

    checks = {
        "Streaming funktioniert": (
            token_count > 0 and len(full_answer.strip()) > 0
        ),
        "Kein <think>-Leak im sichtbaren Output": not think_leaked,
        "Antwort nicht leer/abgeschnitten": len(full_answer.strip()) > 20,
        "Quellen-IDs [S1]/[S2] vorhanden": len(source_ids) > 0,
        "num_predict >= 1024": settings.gen_num_predict >= 1024,
        "think AN, clientseitig gefiltert": has_think,  # Raw-Call bewies think
        "Grounding-LLM antwortet nicht-leer": len(grounding_content) > 0,
        "Grounding positiv = 'Ja'": (
            grounding_content.lower().startswith("ja")
        ),
        "Grounding negativ = 'Nein'": (
            grounding_neg_content.lower().startswith("nein")
        ),
        "Refusal bei unbelegter Frage": (
            is_refusal or confidence_refusal == "rot"
        ),
    }

    all_pass = True
    for check_name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {check_name}")

    print()
    if all_pass:
        print(">>> PHASE 5 VERIFIZIERT <<<")
    else:
        failed = [k for k, v in checks.items() if not v]
        print(f">>> PHASE 5 NOCH NICHT KOMPLETT "
              f"-- {len(failed)} Check(s) fehlgeschlagen <<<")
        for f in failed:
            print(f"  - {f}")

    print()
    print("OFFENER PUNKT: grounding.py except-Default 'return True'")
    print("-> Empfehlung: auf 'return False' (Fail-Closed) drehen.")


if __name__ == "__main__":
    asyncio.run(main())
