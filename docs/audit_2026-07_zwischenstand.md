# Zwischenaudit Halle-Gehirn — Juli 2026

> Vollständiges Audit über Extraction, Chunking, Ingest/Indexierung, Retrieval-Anbindung,
> Generierung, API und Frontend. Fokus: **Masterarbeiten im BTU-Format** als Primärkorpus.
> Jeder Befund mit `file:line`. Umsetzungs-Prompts: siehe Abschnitt „Arbeitspakete".

## Executive Summary

Der Spine (Phase 0–6) steht und ist architektonisch sauber (Protocols, Fail-Fast-Validierung,
deterministische Chunk-IDs, Collection-Isolation). Das Audit findet jedoch **vier gravierende
Lücken**, die den Demonstrator-Wert direkt mindern:

| # | Befund | Schwere | Schicht |
|---|--------|---------|---------|
| A1 | **Kurzfassung/Abstract wird als Front-Matter verworfen** — der inhaltlich dichteste Teil jeder Abschlussarbeit fehlt im Index | 🔴 hoch | Chunk-Filter |
| A2 | **Tail-Matter-Filter verwirft ALLE Tabellen** (positional, Tabellen hängen am Listenende) — Ergebnistabellen von Masterarbeiten gehen verloren | 🔴 hoch | Chunker+Filter |
| A3 | **Context-Enricher ist nicht verdrahtet** — Contextual Retrieval (CLAUDE.md: „Default an, +5–15 % Recall") existiert produktiv nicht; `context_prefix` ist immer `None` | 🔴 hoch | Ingest |
| A4 | **Streaming-Pfad verwirft Validation-, Grounding- und PII-Redaktions-Ergebnisse** — die UI nutzt ausschließlich Streaming, d. h. die Anti-Halluzinations-/PII-Stufen 8–10 sind im Realbetrieb wirkungslos | 🔴 hoch (Security) | Orchestrator |

Dazu kommen strukturelle Schwächen mittlerer Schwere (Kapitel-Hierarchie einstufig, keine
Seitenzahlen für Fließtext, kein Delta-Ingest, API-Schema-Drift) — vollständige Liste unten.

---

## 1. Befunde: Extraction (Schicht 1)

**Fluss:** `ManualLoader.discover()` → Suffix-Dispatch → `DoclingExtractor` (primär, fail-closed
mit >20 %-Seitenverlust-Schwelle) → `pymupdf4llm`-Fallback. Manifest überschreibt Titel und
liefert alle Facetten (`manual_loader.py:257-290`).

| Befund | Schwere | Ort |
|---|---|---|
| Heading-Erkennung hängt vollständig am Markdown-`#`. Liefert das Backend keine Headings, entsteht **eine** Riesen-Section — Front-/Tail-Filter greifen dann gar nicht (Titelblatt + Erklärung landen im Index) | 🟠 mittel | `chunk_helpers.py:18`, `chunk_filter.py:199-200` |
| Seitenzahlen nur für Tabellen/Abbildungen; Body-Chunks haben nie `page` — „S. X"-Zitate unmöglich | 🟠 mittel | `chunker.py:62`, `docling_extractor.py:170,460-465` |
| `boilerplate.clean()` (Kopf-/Fußzeilen, Seitenzahlen) wird im PDF-Fluss **nie aufgerufen** | 🟠 mittel | `boilerplate.py:86-119` (kein Aufrufer) |
| BTU-Titelblatt-Metadaten (Autor, Betreuer/Gutachter, Studiengang, Abgabedatum) werden nicht extrahiert; `autor`-Facette bleibt praktisch leer, alles wird manuell ins Manifest getippt | 🟡 niedrig | `docling_extractor.py:554-560`, `metadata_detector.py` |
| OCR-Default `true` + TableFormer `accurate` → reale `std::bad_alloc`-/Performance-Probleme bei großen PDFs; Abschaltung nur manuell je Manifest-Eintrag | 🟡 niedrig | `config.py:58-59` |
| `_extract_single` schluckt jede Exception (fail-forward) — ein komplett gescheitertes Dokument verschwindet still (nur Log) | 🟡 niedrig | `manual_loader.py:221-227` |

## 2. Befunde: Chunking (Schicht 2)

| Befund | Schwere | Ort |
|---|---|---|
| **A1**: Front-Matter-Filter verwirft alles vor dem ersten nummerierten Kapitel — inkl. **Kurzfassung/Abstract** (steht bei BTU-Arbeiten vor „1 Einleitung"). Keine Whitelist | 🔴 hoch | `chunk_filter.py:189-200,261-262` |
| **A2**: Tabellen-Chunks werden ans Listenende gehängt (`chunker.py:117-132`) und fallen positional hinter den Tail-Matter-Cutoff → `filter_chunks` verwirft sie alle. Regression dokumentiert als strict-xfail `test_content_tables_survive_tail_matter` | 🔴 hoch | `chunk_filter.py:265-266` |
| Nur **ein** Heading-Level je Section (`headings=[heading_text]`) — keine Eltern-Kette H1›H2›H3. `breadcrumb` im Payload ist dadurch immer einstufig | 🟠 mittel | `chunk_helpers.py:79-92` |
| Tabellen-Chunks: `headings=[]` → `breadcrumb=None`; `char_start=0/char_end=len` sind Fake-Offsets, landen so in Qdrant | 🟠 mittel | `chunker.py:125-132` |
| `char_end` bei Satz-Split approximativ (Whitespace-Rekonstruktion via `" ".join`) | 🟡 niedrig | `chunker.py:246-248` |

## 3. Befunde: Ingest / Indexierung (Schicht 2/3)

| Befund | Schwere | Ort |
|---|---|---|
| **A3**: `OllamaContextEnricher.enrich` hat **keinen einzigen Aufrufer** im Ingest-Fluss. `context_prefix` immer `None`, `text == text_raw` immer | 🔴 hoch | `ingest.py:467-472` (kein enrich), `context_enricher.py` |
| Kein Stale-Delete/Delta: geänderte Datei → neuer `source_hash` → neue Punkt-IDs, **alte Punkte bleiben stehen** (Dubletten). Kein Skip unveränderter Dokumente — jeder Lauf re-embedded alles | 🟠 mittel | `ingest.py`, `indexer.py:30-54`, `reindex.py` |
| Ollama down beim Embedding → gesamter Lauf crasht ohne Teil-Upsert/Checkpoint | 🟠 mittel | `indexer.py:50`, `ollama_embedder.py:108` |
| `source_url` hart `None`, `lang` hart `"de"` | 🟡 niedrig | `ingest.py:322-324` |

**ChunkPayload-Befüllung real:** `context_prefix` und `source_url` immer `None`; `page` nur
Tabellen; `breadcrumb` nur Body-Chunks, nur einstufig, bei Tabellen `None`.

## 4. Befunde: Generierung / API / Frontend (Schicht 4/5)

| Befund | Schwere | Ort |
|---|---|---|
| **A4**: `run_stream` ruft Validation/Grounding/Output-Guardrail auf, **verwirft aber alle Ergebnisse**: kein `cleaned_answer`, kein Grounding-Verdict im done-Event, **keine PII-Redaktion** (Non-Stream-Pfad redigiert, `orchestrator.py:158,167-168`). UI nutzt nur Streaming | 🔴 hoch | `orchestrator.py:273-280` |
| Schema-Drift: `_build_sources` liefert `datei/doc_type/breadcrumb`, `schemas.Source` kennt sie nicht → `/chat` (Pydantic) verliert die Felder, `/chat/stream` (raw dict) liefert sie — zwei APIs, zwei Verträge | 🟠 mittel | `schemas.py:21-29` vs. `orchestrator.py:364-380` |
| LLM-Prompt-Kontext enthält nur `titel + text` — ohne `page`/`breadcrumb` kann KI Fabrik Scout nie „(S. 42, Kap. 3.2)" zitieren | 🟠 mittel | `prompts.py:97-112` |
| Facetten-Filter: API + Retriever können `filters`, das Chat-UI sendet nie welche — die Kern-Taxonomie ist im Chat unsichtbar | 🟠 mittel | `streamlit_app.py:172-175` |
| `primary_color` tote Konfig (UI hardcodiert `#c41230`), `bot_name` hardcodiert, SSE-Parse ohne `JSONDecodeError`-Schutz | 🟡 niedrig | `streamlit_app.py:59-62,76,181`, `config.py:101-102` |
| Rate-Limiter + Session-Dict wachsen unbegrenzt (kein Eviction), Admin-Key-Vergleich nicht konstantzeit, `/admin/reindex+eval` Platzhalter | 🟡 niedrig | `main.py:64-75`, `orchestrator.py:65`, `admin.py:37,51-71` |
| Kein Preact-Widget / `frontend/` — Phase 7 offen; `public/` enthält nur Logos | ℹ️ geplant | — |

## 5. Stärken (beibehalten)

- Fail-closed-Extraktion mit Seitenverlust-Schwelle + Fallback-Kaskade
- Fail-Fast-Manifest-Validierung gegen Vokabular + Enums vor jedem I/O
- Deterministische Chunk-IDs, Right-to-Erasure, Collection-Isolation
- Harte Token-Garantie im Chunker (kein Chunk > max, mehrstufige Fallbacks)
- Deutsch-optimierter Satz-Splitter mit Abkürzungsschutz
- Chunk-Qualitäts-Eval (`eval/chunk_quality.py` + Report) als Regressionsnetz

---

## Arbeitspakete & Umsetzungs-Prompts

Reihenfolge nach Nutzen/Risiko. Jeder Prompt ist self-contained (für eine frische
Claude-Code-Session oder als Auftrag in einer laufenden).

### WP1 — BTU-Masterarbeiten sauber chunken (Chunking & Filter) 🔴

```text
Kontext: docs/audit_2026-07_zwischenstand.md, Befunde A1, A2 + Kapitel-Hierarchie.
Repo halle-gehirn, betrifft pipeline/chunk_helpers.py, pipeline/chunk_filter.py,
pipeline/chunker.py, eval/chunk_quality.py, tests/test_chunk_quality.py.

Aufgabe — drei Fixes, test-getrieben:
1. KURZFASSUNG RETTEN: chunk_filter.py — Whitelist-Set _ABSTRACT_HEADINGS
   {kurzfassung, abstract, zusammenfassung, summary} (case-insensitive, nach
   _strip_section_number). Chunks, deren Heading-Kette ein Whitelist-Heading
   enthält, überleben den Front-Matter-Drop. Achtung: ein nummeriertes
   „7 Zusammenfassung" ist regulärer Inhalt und zählt nicht als Front-Matter.
2. TABELLEN RETTEN: Der positionale Front-/Tail-Matter-Drop darf is_table-Chunks
   nicht treffen (Tabellen hängen chunker-bedingt am Listenende, ihr Index ist
   positional bedeutungslos). Inhaltsregeln (TOC, dot-leaders) gelten weiter.
   Danach: strict-xfail test_content_tables_survive_tail_matter in
   tests/test_chunk_quality.py in einen regulären Test umwandeln.
3. KAPITEL-HIERARCHIE: chunk_helpers.split_sections führt einen Heading-Stack
   nach #-Level: Section.headings = vollständige Eltern-Kette top→leaf
   (z. B. ["2 Grundlagen", "2.1 Kinematik"]). ingest baut daraus automatisch
   den mehrstufigen breadcrumb (" > ".join). Alle headings[0]-Nutzer prüfen:
   Logging in chunker.py auf headings[-1] (eigenes Heading) umstellen;
   chunk_filter iteriert bereits über alle headings — verifizieren, dass
   Front-Matter-Erkennung (numbered heading) mit Ketten korrekt bleibt.

Eval erweitern: build_abschlussarbeit() in tests/test_chunk_quality.py um
Kurzfassung (vor Kap. 1) und ein Unterkapitel (### 2.1 …) ergänzen; Bänder
in TestChunkQualityBands nachziehen. scripts/eval_chunk_quality.py laufen
lassen und VOR/NACH-Kennzahlen berichten.

Definition of Done: pytest tests/ grün (xfail entfernt), ruff+mypy grün,
Report zeigt: Tabellen überleben Filter, Kurzfassung im Index, breadcrumb
mehrstufig. TASKS.md aktualisieren.
```

### WP2 — Ingester sauber: Contextual Retrieval verdrahten + Delta-Ingest 🔴

```text
Kontext: docs/audit_2026-07_zwischenstand.md, Befund A3 + Delta-Ingest.
Betrifft pipeline/ingest.py, pipeline/context_enricher.py, pipeline/indexer.py,
src/scripts/reindex.py, vector_store/qdrant_client.py.

Aufgabe:
1. ENRICHER VERDRAHTEN: OllamaContextEnricher in den Ingest-Fluss einbauen
   (Settings.use_contextual_retrieval respektieren). Architektur: Enrichment als
   async Stage zwischen run_ingest und embed_and_upsert in reindex.py (oder in
   embed_and_upsert selbst), da _process_entry sync ist. Graceful Degradation:
   Ollama nicht erreichbar → structlog-warning je Dokument, context_prefix
   bleibt None, Ingest läuft weiter (kein Crash). Tabellen-Chunks werden MIT
   angereichert (Kontextsatz erklärt, wozu die Tabelle gehört).
2. DOC-SUMMARY VERBESSERN: context_enricher nutzt body_md[:500] — auf
   Titel + Kurzfassung/erste Section erweitern (bessere Kontextsätze).
3. STALE-DELETE: Vor Upsert eines Dokuments alle Qdrant-Punkte mit gleichem
   payload.datei aber anderem source_hash löschen (Filter-Delete in
   qdrant_client ergänzen, analog delete_by_source_hash).
4. SKIP UNVERÄNDERT: --delta Flag in reindex.py — Dokumente, deren source_hash
   bereits vollständig indexiert ist, überspringen (list_indexed_documents
   nutzen); IngestStats um docs_unchanged erweitern.

Tests mit gemocktem Ollama/Qdrant (bestehender Stil in test_ingest.py):
enrich wird aufgerufen wenn use_contextual_retrieval=true, prefix landet in
payload.text (prefix + \n\n + text_raw), Degradation ohne Crash, Stale-Delete
löscht alte Hashes, --delta überspringt. DoD: pytest/ruff/mypy grün, TASKS.md.
```

### WP3 — Seiten-Provenienz & Boilerplate (Extraction) 🟠

```text
Kontext: Audit Kap. 1/2 — Body-Chunks ohne page, boilerplate.clean ungenutzt.
Betrifft extraction/docling_extractor.py, pipeline/chunker.py, ingest.py.

Aufgabe:
1. PAGE-MAP: DoclingExtractor exportiert zusätzlich eine Seiten-Karte
   [(char_offset_start, page_no), …] aus den Docling-Element-Provenienzen
   (prov[0].page_no je Element beim Markdown-Export mitschreiben) und legt sie
   in ExtractedDoc (neues Feld page_map: list[tuple[int,int]]).
2. Chunker mappt char_start jedes Body-Chunks über die page_map auf page
   (binäre Suche; None wenn keine Karte, z. B. pymupdf4llm-Fallback ohne
   page_chunks — dort pymupdf4llm page_chunks=True nutzen und Karte bauen).
3. BOILERPLATE: remove_page_numbers + remove_repeated_headers aus
   boilerplate.py nach der Extraktion auf body_md anwenden (Konfig-Flag,
   Default an) — Offsets der page_map dabei konsistent halten (Reihenfolge:
   erst cleanen, dann Karte bauen, sonst Karte nach dem Cleaning neu ableiten).
4. Tabellen-Chunks: char-Fake-Offsets (0..len) durch None ersetzen
   (ChunkPayload.char_start/end optional machen) statt falsche Werte zu
   speichern.

DoD: test mit synthetischem Docling-Dokument (gemockt) + echter Test-PDF
(tests/data/test_anlage_roboter.pdf): >80 % der Body-Chunks tragen page.
Eval-Report um page_coverage-Kennzahl erweitern. pytest/ruff/mypy grün.
```

### WP4 — BTU-Titelblatt-Parser (Metadaten-Autofill) 🟠

```text
Kontext: Audit Kap. 1 — Titelblatt-Metadaten ungenutzt, autor-Facette leer.
Betrifft extraction/metadata_detector.py, manifest/editor.py, data/vokabular.yaml.

Aufgabe: Regelbasierter Titelblatt-Parser für BTU-Abschlussarbeiten in
metadata_detector.py (erste 2 Seiten, pypdf bereits vorhanden):
- autor: Muster „vorgelegt von|eingereicht von|von: <Name>" + pypdf /Author
- betreuer/gutachter → ansprechperson-Vorschläge: „Betreuer|1./2. Gutachter|
  Prüfer: (Prof.|Dr.)? <Name>" — gegen vokabular.yaml-Registry matchen
  (Nachname-lowercase-Slug), unbekannte Namen als Vorschlag „neu anlegen?"
- studiengang/fakultät: „Studiengang <X>", „Fakultät <N>"
- jahr: „Cottbus, den TT.MM.JJJJ" bzw. Datum auf Titelblatt — hat Vorrang
  vor der bisherigen Erste-Jahreszahl-Heuristik (metadata_detector.py:214-227)
- grad: „Masterarbeit|Bachelorarbeit|Master Thesis" (existiert, verifizieren)
MetadataSuggestion um autor/studiengang erweitern; Manifest-Editor zeigt die
Vorschläge zur Bestätigung an (Human-in-the-Loop, KEIN Auto-Write).
Matrikelnummern explizit NICHT extrahieren (DSGVO).

DoD: Tests mit synthetischen Titelblatt-Texten (3 Varianten BTU-Layout),
pytest/ruff/mypy grün, TASKS.md.
```

### WP5 — Streaming-Härtung: Validation/Grounding/PII 🔴 (Security)

```text
Kontext: Audit Befund A4 — orchestrator.py:273-280 verwirft im Stream-Pfad
die Ergebnisse von Validation, Grounding und PII-Check; Non-Stream-Pfad
(orchestrator.py:158-168) wendet sie an. Die UI nutzt nur Streaming.

Aufgabe:
1. run_stream: nach der Generierung validation.cleaned_answer und
   PII-Redaktion auf full_answer anwenden. Da Tokens bereits gestreamt sind:
   done-Event um final_answer (bereinigt) + Flags erweitern
   (validation_passed, grounding_score, pii_redacted); das Frontend ersetzt
   den gestreamten Text durch final_answer, wenn er abweicht.
2. Grounding-Ergebnis in done-Event und Audit-Log aufnehmen (bisher verworfen).
3. Memory soll die BEREINIGTE Antwort speichern, nicht full_answer roh
   (orchestrator.py:267-270 verschieben/anpassen).
4. streamlit_app.py: done-Event auswerten (final_answer ersetzen),
   json.loads je SSE-Zeile mit try/except JSONDecodeError absichern.

Tests: test_orchestrator.py — Stream-Pfad mit PII in der Modell-Antwort →
done-Event enthält redigierten final_answer; Grounding-Score im done-Event.
DoD: pytest/ruff/mypy grün, verify_phase5-Skript-Lauf beschreiben, TASKS.md.
```

### WP6 — API-Vertrag & Frontend-Politur 🟠

```text
Kontext: Audit Kap. 4 — Schema-Drift, fehlende Facetten-Filter, Branding.
Betrifft api/schemas.py, generator/prompts.py, ui/streamlit_app.py, config.py.

Aufgabe:
1. schemas.Source um datei, doc_type, breadcrumb erweitern → /chat und
   /chat/stream liefern identische Quellen-Felder (Vertrags-Gleichheit testen).
2. prompts.format_context: je Quelle „[n] titel (S. page, breadcrumb)" in den
   LLM-Kontext geben, Prompt-Instruktion: Seitenangabe in Citations übernehmen.
3. Chat-UI: Sidebar-Facetten-Filter (doc_type, bereich, anlage, jahr) aus
   vokabular.yaml/Enums, als filters an die API senden; aktive Filter anzeigen.
4. Branding aus Config: bot_name + primary_color aus Settings lesen (BTU-Rot
   als Default in .env.example eintragen statt #000000-TODO), Ampel-/
   Akzentfarben daraus ableiten.
5. Quellen-Snippets serverseitig auf ~300 Zeichen kürzen (orchestrator
   _build_sources) statt ganze Chunks auszuliefern.

DoD: pytest (test_api Vertrags-Test /chat == /chat/stream Felder), ruff/mypy
grün, Screenshot der UI mit Filtern + Quellen inkl. Seite/Kapitel, TASKS.md.
```

### WP7 — Ops-Härtung (klein) 🟡

```text
Kontext: Audit Kap. 4 unten. Betrifft api/main.py, api/routes/admin.py,
pipeline/orchestrator.py, CI.

Aufgabe: (1) Rate-Limiter-Eviction (leere IP-Buckets aufräumen) + Hinweis-
Kommentar Multi-Worker-Grenze; (2) Session-Memory-Eviction (LRU/TTL, z. B.
max 500 Sessions); (3) Admin-Key-Vergleich via secrets.compare_digest;
(4) CI: tiktoken cl100k_base offline cachen (TIKTOKEN_CACHE_DIR + Datei ins
CI-Cache, s. Hinweis in TASKS.md Phase 8); (5) manual_loader fail-forward:
gescheiterte Dokumente in IngestStats.errors sichtbar machen statt nur Log.
DoD: pytest/ruff/mypy grün, TASKS.md.
```

---

## Empfohlene Reihenfolge

**WP1 → WP2** (Masterarbeiten-Korpus sauber rein — der erste Schritt laut Projektleitung),
dann **WP5** (Security, vor jeder Demo), **WP3** (Seitenzitate = Demonstrator-Wow),
**WP6**, **WP4**, **WP7**. Nach WP2 und WP3 jeweils Reindex + `scripts/eval_chunk_quality.py`
als Regressionsnachweis; nach WP5/WP6 die Golden-Q&A-Baseline (Phase 8) aufsetzen.
