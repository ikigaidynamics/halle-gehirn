# TASKS.md — Halle-Gehirn

Backlog je Phase. `[x]` erledigt · `[ ]` offen. Reihenfolge des ersten Builds:
0 → 1 → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 7 → 10.

## Phase 0 — Bootstrap  ✅
- [x] Verzeichnisstruktur + Package-Inits
- [x] `pyproject.toml` (hatchling, Python 3.12) + Dependencies
- [x] `config.py` (pydantic-settings, alle .env-Variablen typisiert)
- [x] `.env.example`
- [x] `pipeline/protocols.py` (alle Stage-Interfaces)
- [x] `vector_store/schema.py` (Qdrant-Hybrid + **Taxonomie**: Enums, ChunkPayload, Indizes)
- [x] `data/vokabular.yaml` + `data/manifest.yaml` (Vorlage) + `docs/taxonomie.md`
- [x] `ruff.toml` + `mypy.ini` + `observability/logging_config.py`
- [x] `PLANNING.md` + `TASKS.md` + `README.md` + `.gitignore`
- [x] `pip install -e ".[dev]"` lauffähig · `ruff check` + `mypy` grün auf den Stubs

## Phase 1 — Extraction (Docling) + Crawler
- [x] `extraction/base.py` (Extractor-Protocol + ExtractedDoc + TableBlock)
- [x] `extraction/docling_extractor.py` (PRIMÄR — DoclingExtractor)
- [x] `extraction/{html_extractor,boilerplate,title_extractor,manual_loader}.py`
- [x] `scraper/{fetcher,js_fetcher}.py` (sekundär, Delta + Playwright)
- [x] `ruff check` + `mypy` grün auf allen Phase-1-Modulen (70 source files)
- [x] Tests: Docling-Extraktion, Boilerplate, Delta (16 tests, alle gruen)

## Phase 2 — Indexierung  ✅
- [x] `pipeline/sentence_splitter.py` (deutsch, Abkürzungs-Schutz)
- [x] `pipeline/chunker.py` (MarkdownChunker: Heading-Sections + Satz-Split + tiktoken)
- [x] `pipeline/context_enricher.py` (Contextual Retrieval via Ollama)
- [x] `embeddings/{provider,ollama_embedder,sparse_embedder,colbert_embedder}.py`
- [x] `pipeline/ingest.py` — **liest `data/manifest.yaml`, validiert Slugs gegen `vokabular.yaml`**
- [x] `src/scripts/reindex.py`
- [x] `ruff check` + `mypy` grün auf 70 source files
- [x] Tests: Splitter (10), Chunker (9), Ingest (16) — 35 Tests, alle gruen
- [x] End-to-End-Verifikation: Test-PDF → 3 Chunks, ChunkPayload komplett, Sparse BM25 OK, Fail-Fast OK

## Phase 3 — Vector-Store (Qdrant Hybrid)  ✅
- [x] `vector_store/qdrant_client.py` (Factory, upsert, hybrid_query, snapshot, erasure, delete_by_source_hash)
- [x] `src/scripts/snapshot.py` (create/list CLI)
- [x] `src/scripts/reindex.py` verdrahtet: --reset loescht/erstellt NUR QDRANT_COLLECTION
- [x] Tests: Collection (4), Upsert+Retrieve (5), Hybrid-Query fusioniert (3), Erasure (2), Filter (3) — 17 Tests, alle gruen
- [x] End-to-End-Verifikation: Test-PDF → Embed → Upsert halle_wissen → Hybrid-Query (RRF, 3 Treffer mit Scores) → --reset beweist: nur halle_wissen angefasst, cottbus_buergerservice + btu_transfer unberuehrt

## Phase 4 — Retrieval  ✅
- [x] `embeddings/reranker.py` (Logprobs-Reranker, Ollama-basiert)
- [x] `retrieval/{query_transform,router,retriever}.py` (HybridRetriever, KeywordRouter, OllamaQueryTransformer)
- [x] `pipeline/stages/confidence.py` (Ampel: gruen/gelb/rot)
- [x] Tests: Hybrid+Rerank, Confidence-Schwellen, Router (test_retrieval.py, alle gruen)
- [x] End-to-End-Verifikation: Live-Query mit Reranking + Confidence-Gate

## Phase 5 — Generierung  ✅
- [x] `generator/{ollama_client,prompts,smalltalk,memory}.py` (Persona: Jarvis, SSE-Streaming, Think-Tag-Filterung)
- [x] `pipeline/stages/{validation,grounding,guardrails}.py` (URL-Whitelist, Faithfulness, Prompt-Injection-Abwehr, PII-Redaktion)
- [x] Tests: Refusal, Citation-Pflicht, Prompt-Injection, Smalltalk (test_generation.py, alle gruen)
- [x] End-to-End-Verifikation: Live-Generierung mit Streaming + Grounding-Check

## Phase 6 — API  ✅
- [x] `pipeline/{factory,orchestrator}.py` (QueryPipeline, QueryOrchestrator mit 10-Stage-Pipeline)
- [x] `api/{schemas,main, routes/{chat,health,admin}}.py` (FastAPI, CORS, Rate-Limit, SSE)
- [x] `governance/audit.py` (StructlogAuditLogger)
- [x] `ui/streamlit_app.py` (Chat-UI mit SSE-Streaming, Konfidenz-Ampel, Quellen)
- [x] Tests: /chat(/stream), /ready, Admin-Auth (test_api.py + test_orchestrator.py, 19 Tests gruen)
- [x] Live-Verifikation: /health=ok, /ready=ready (Qdrant+Ollama true), Admin 401/200, Chat JSON + SSE-Streaming mit Quellen + Citations

## Phase 8 — Evaluation  (vorgezogen)
- [ ] `data/eval/golden_qa.yaml` + `eval/{golden_qa,metrics,runner}.py`
- [ ] `src/scripts/eval_queries.py` → Baseline-Report
- [ ] Regression-Gate (CI)
- [ ] Schwier-Arbeit (`Masterarbeit_PhilippSchwier_5009038.pdf`) als digitales Original
      mit Textebene beschaffen (Aaron). PDF ist Text-als-Kurven (0 extrahierbarer Text,
      Docling Serve macht OCR → Zahlensalat bei Vergleichstabellen S. 27-28, 87-88).
      Reranker filtert Salat-Chunks zuverlaessig (Score 0.0), daher harmlos.
      Optional: Statistik-Zahlensalat-Chunks per Heuristik filtern.
- [x] `eval/chunk_quality.py` (ChunkQualityReport: Token-Verteilung, Fragmente,
      Heading-/Zeichen-Abdeckung, Tabellen-Integritaet) + `tests/test_chunk_quality.py`
      (Invarianten + Qualitaetsbaender) + `scripts/eval_chunk_quality.py` (Report)
- [x] **DEFEKT behoben (WP1):** Tabellen fallen nicht mehr unter den positionalen
      Tail-/Front-Matter-Drop (`chunk_filter.py`: is_table-Ausnahme); ehem.
      xfail `test_content_tables_survive_tail_matter` ist jetzt regulaerer Test.
- [x] **WP1 — BTU-Masterarbeiten sauber chunken** (siehe
      `docs/audit_2026-07_zwischenstand.md`): Kurzfassung/Abstract ueberleben
      den Front-Matter-Filter (`_ABSTRACT_HEADINGS`-Whitelist) · Heading-Ketten
      top→leaf in `split_sections` (mehrstufige Breadcrumbs) · Eval-Korpus um
      Kurzfassung + Unterkapitel erweitert (70 Chunk-Tests gruen).
- [x] **WP2 — Ingester sauber (Contextual Retrieval + Delta):**
      Enricher in `run_ingest` verdrahtet (3 Phasen: Prepare → Enrich →
      Payloads; graceful bei Ollama-Ausfall; Tabellen werden mit angereichert) ·
      `build_doc_summary` bevorzugt Kurzfassung/Abstract fuer den Kontext-Prompt ·
      Manifest-Titel ueberschreibt doc.title auch im Ingest-Pfad ·
      `delete_stale_chunks` (alte Hashes + ueberzaehlige Indizes, Aufruf NACH
      Upsert) · `--delta`-Flag in reindex.py (skip via source_hash,
      `docs_unchanged` in IngestStats) · 14 neue Tests (gemockter Ollama/Qdrant).
- [x] **WP5 — Streaming-Haertung (Audit-Befund A4):** run() und run_stream()
      teilen sich `_finalize_answer` (Validation → Grounding → PII-Redaktion) —
      der Stream-Pfad wendet die Ergebnisse jetzt AN statt sie zu verwerfen.
      Done-Event traegt `final_answer` (autoritativ, bereinigt/redigiert) +
      `pii_redacted`/`grounding_score`/`grounded`/Citation-Zaehler; Client
      (Streamlit) ersetzt den gestreamten Rohtext und parst SSE-Zeilen robust
      (JSONDecodeError-Schutz). Memory speichert die BEREINIGTE Antwort (beide
      Pfade). Audit-Log um grounding_score + pii_redacted erweitert.
      9 neue Tests (test_stream_hardening.py).
- [x] **WP3 — Seiten-Provenienz & Boilerplate:** Neues Modul
      `extraction/page_map.py` (build_page_map: monotones Element-Matching;
      join_pages_with_map: exakte Map fuer seitenweise Backends;
      remove_cross_page_repeats). Docling-Pfad: Element-Provenienz →
      Page-Map; pymupdf4llm-Fallback: `page_chunks=True` → exakte Map.
      Chunker weist Body-Chunks Seiten zu (page_for_offset). Boilerplate-
      Cleaning (Kopf-/Fusszeilen, Seitenzahlen) jetzt verdrahtet
      (BOILERPLATE_CLEAN, Default an). Tabellen-Fake-Offsets → None
      (ChunkPayload.char_start/end optional). Eval um page_coverage
      erweitert. 15 neue Tests; E2E Test-PDF: page_coverage 100 %.
- [x] **WP6 — API-Vertrag & Frontend-Politur:** `schemas.Source` um
      datei/doc_type/breadcrumb erweitert (Vertrags-Test: /chat ==
      /chat/stream) · Snippets serverseitig auf ~300 Zeichen gekuerzt ·
      `format_context` gibt Seite + Kapitel-Breadcrumb an das LLM
      („[S1] Titel (S. 12 · Kapitel)"; Regel 7: Quellenliste mit
      Seitenangabe) · Sidebar-Facetten-Filter (doc_type/bereich/anlage/
      jahr, `ui/_filter_sidebar.py`) gehen als filters an die API ·
      Branding aus Config (BOT_NAME, PRIMARY_COLOR=#c41230 statt
      #000000-TODO). 8 neue Tests (test_api_contract.py).
- [x] **WP4 — BTU-Titelblatt-Parser:** Neues Modul `extraction/titelblatt.py`
      (Autor „vorgelegt/eingereicht von", Betreuer/Gutachter/Pruefer,
      Studiengang, Abgabedatum→Jahr; `nachname_slug` fuer Registry-Match).
      In `detect_metadata` integriert: Datum schlaegt Erste-Jahreszahl-
      Heuristik, bekannte Personen → Slugs, unbekannte → Vorschlaege
      (Human-in-the-Loop, kein Auto-Write); Ingest-UI zeigt die Vorschlaege.
      Matrikelnummern bewusst NICHT extrahiert (DSGVO). 14 neue Tests
      (3 Titelblatt-Varianten).
- [x] **WP7 — Ops-Haertung:** Rate-Limiter-Eviction (verwaiste IP-Buckets,
      Multi-Worker-Hinweis) · Session-Memory LRU (max 500, OrderedDict) ·
      Admin-Key via `secrets.compare_digest` (konstantzeit) · manual_loader
      Fail-forward auf WARNING sichtbar · tiktoken-Offline-Cache
      (`scripts/cache_tiktoken.py` + conftest zeigt auf `.tiktoken_cache/`,
      Mirror-Fallback fuer gesperrte Egress → CI/Offline-Collection laeuft).
      7 neue Tests (test_ops_hardening.py).

- [x] **WP8 — Remote Docling Serve** (feature/docling-serve, gemergt):
      `DoclingExtractor` spricht optional einen docling-serve-HTTP-Endpoint
      an (`DOCLING_SERVE_URL`, POST /v1/convert/file, to_formats md+json).
      `_build_result_from_remote` baut ExtractedDoc aus `json_content` —
      inkl. WP3-Page-Map (aus texts-Provenienz), Tabellen (grid→Markdown,
      Caption via $ref) und Boilerplate-Cleaning. Fallback auf lokalen
      Docling bei ConnectError/Timeout; status=failure → ExtractionError.
      `deterministic_chunk_id` nach qdrant_client verschoben (Re-Export in
      ingest, kein Zirkelimport). 4 neue Tests (gemocktes HTTP).

- [x] **WP9 — Bild-Integration (feature/images):**
      Docling Serve liefert Bilder per `image_export_mode=embedded` (Base64
      data-URIs). Shared Helper `extraction/figure_utils.py` (DRY: save_figures,
      extract_figures_local, extract_figures_from_serve). `pipeline/figure_linker.py`
      verknuepft FigureBlocks mit Chunks (primaer: Caption-Nummern-Regex
      DE/EN, Fallback: Seitenzuordnung). ChunkPayload + Chunk um `figure_refs`,
      `figure_captions`, `figure_description` (VLM-Reserve) erweitert.
      Caption-Fold: Captions werden an `text` (nicht `text_raw`) angehaengt
      fuer Embedding-Retrievability. Erasure: `delete_by_source_hash` entfernt
      auch `data/figures/{hash[:16]}/`. UI: `Source`-Schema + `_build_sources`
      + Streamlit `_render_sources` zeigen Bilder via `st.image()`.
      27 neue Tests (test_figures.py); ruff+mypy gruen.

- [x] **WP10 — Hierarchisches Section-Merging + Ingester-Fortschritt:**
      `merge_sibling_sections()` in `chunk_helpers.py`: Greedy-Merge
      aufeinanderfolgender Geschwister-Sektionen (gleicher Eltern-Heading-Pfad
      oder Eltern-Kind-Beziehung) bis `target_tokens`. Strukturelle Headings
      (Verzeichnisse, Anhang, Kurzfassung/Abstract) bleiben als eigene Chunks
      erhalten (`_UNMERGEABLE_HEADINGS`). In `chunker._chunk_body()` verdrahtet
      (nach `split_sections`, vor Per-Section-Chunking); char_end auf
      Body-Laenge begrenzt.
      Callback-basierter Ingest-Fortschritt: `pipeline/progress.py`
      (`ProgressEvent` + `ProgressCallback`), verdrahtet in `run_ingest()`
      und `embed_and_upsert()`. Streamlit-UI (`_indexieren_tab.py`) zeigt
      pro Dokument: Fortschrittsbalken, ETA, Sample-Chunk, Chunking-Strategie,
      Abbildungs-Thumbnails. Embed-Phase: Queue-basierte Thread-Kommunikation.
      11 neue Merge-Tests + 1 Chunker-Test aktualisiert; ruff+mypy gruen.

**Zwischenaudit vollstaendig abgearbeitet (WP1–WP7).** Offen bleiben nur
4 vorbestehende Test-Failures (Docling-Tabellen + Reranker-Fallback,
Umgebungs-Drift, unabhaengig vom Audit) und ein latenter mypy-Hinweis
in `manual_loader._extract_single` (Extractor-Protocol ohne do_ocr).

## Phase 9 — Compliance & Security  (vorgezogen)
- [ ] `governance/{audit,consent,erasure}.py`
- [ ] Prompt-Injection-/Jailbreak-Suite in Eval-Regression
- [ ] `docs/`: AVV-Template, TOMs, Model-Card, EU-AI-Act-Art.-4-Checkliste

## Phase 7 — Frontend (Demonstrator-Widget)
- [ ] `frontend/widget/` (Preact+Tailwind, <100 KB, Streaming, Quellen, Konfidenz)
- [ ] Branding: **Jarvis**, `PRIMARY_COLOR` (BTU-Hausfarbe)

## Phase 10 — Deployment & Observability
- [ ] `docker-compose.yml`, `Caddyfile`, `ecosystem.config.js`
- [ ] `observability/tracing.py` (OTEL), Prometheus/Grafana, Backup

## Backlog (nach Eval-Baseline)

- [ ] **Frontend-/Backend-Caching fuer Admin-UI:** Bestand + Chunk-Viewer-Daten
      im Frontend-State halten statt bei jedem Tab-Wechsel neu zu fetchen.
      Cache-Invalidierung nach Ingest/Delete/Chunk-Toggle PFLICHT
      (Diagnose-Werkzeug muss echten Indexzustand zeigen). Risikoarm, evtl.
      vorziehbar.
- [ ] **Semantisches Antwort-Caching fuer den Chatbot** (Refs: ACM 3768628,
      arxiv 2404.12457, Redis semantic cache). VORSICHT: hohe
      Aehnlichkeitsschwelle noetig, sonst bekommt eine Frage die Antwort
      einer nur aehnlichen Frage → ungegroundete Falschantwort, untergraebt
      die Anti-Halluzinations-Kette. Cache muss Quellen+Grounding mitfuehren;
      Wirkung erst mit Eval-Harness messbar. NUR nach Phase 8.
- [ ] **Abbildungen im ChunkViewer:** ZUERST Bestandsaufnahme — werden bei den
      aktuell ingesteten Dokumenten (jetzt via Docling Serve) Figures
      extrahiert, wo liegen sie (`data/figures/`), sind sie Chunks zugeordnet?
      DANN erst Anzeige im ChunkViewer. Kein Retrieval-Gewinn (Text-basiert),
      reines Anzeige-/Diagnose-Feature.

## Nach dem Spine — Geschwister-Module (siehe PLANNING.md)
- [ ] `norm_store/` — deterministischer Norm-Store
- [ ] `live_data/` — OPC-UA-Snapshot-Reader (anlage-Slugs = API-Geräte-IDs)
- [ ] `agent/` — Perceive-Judge-Report-Loop + Bestätigen/Verwerfen-Eval
