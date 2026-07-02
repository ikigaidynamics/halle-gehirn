# CLAUDE.md — Halle-Gehirn

> Kanonische Stack- und Architektur-Definition für **Halle-Gehirn**. Claude Code liest sie
> zu Beginn **jeder** Aufgabe. Anzeigename des Bots: **Jarvis**. Package: `halle_gehirn`.
> Collection: `halle_wissen`. Sprache: `de`.

---

## 1. Projektüberblick

**Halle-Gehirn** ist das agentische KI-System für die Modellfabrik des Lehrstuhls *KI-gestützte
Automatisierungstechnik* (BTU Cottbus-Senftenberg, Prof. Berger) — ein System, das das dokumentierte
Wissen des Lehrstuhls mit Live-Daten der Halle verbindet, den Zustand gegen Normen prüft und
quellenbelegte Lageberichte mit Handlungsempfehlungen erzeugt (Human-in-the-Loop, lokal & souverän).

**Dieses Repo ist Stufe 1 / Säule 1: die Wissensbasis** — ein lokal-first, DSGVO-konformer RAG-Stack,
der Dokumente (Berichte, Abschlussarbeiten, Handbücher, Anlagendoku, kuratiertes Erfahrungswissen)
per semantischer **und** lexikalischer Suche durchsuchbar macht und Fragen mit belegten Quellen,
exakten Verweisen und Anti-Halluzinations-Garantien beantwortet.

Die weiteren Bausteine des Gesamtsystems (**deterministischer Norm-Store**, **OPC-UA-Live-Daten**,
**agentischer Perceive-Judge-Report-Loop** + operative Eval-Schleife) sind bewusst **noch nicht** Teil
dieses Repos. Sie werden nach dem Spine als protokoll-modulare **Geschwister-Module** ergänzt — keine
Stubs jetzt (siehe PLANNING.md · „Roadmap zum Gesamtsystem").

**Primärquelle sind lokale Dokumente** (`data/manual/`), *nicht* Web-Crawl. Doclings Extractor und der
`manual_loader` stehen im Zentrum; der httpx-Crawler ist sekundär (`b-tu.de` höchstens ergänzend).

---

## 2. Der Stack auf einen Blick

| Schicht | Technologie (kanonisch) | Notiz |
|---|---|---|
| Sprache | Python 3.12 (via `uv`) | Type-Safe, async |
| Extraction-Rückgrat | **Docling** (IBM/DS4SD) | **Primär**: PDF/DOCX/PPTX/XLSX/HTML/Bild — Layout, Tabellen, OCR |
| HTML-Schnellpfad | Trafilatura (optional) | Nur reines HTML |
| Crawler | httpx (+ optional Playwright) | **Sekundär** — Primärquelle sind lokale Docs |
| Chunking | **Docling HybridChunker** + deutscher Splitter | Struktur- + Token-bewusst |
| Kontext-Anreicherung | **Contextual Retrieval** (Anthropic) | Default an; +5–15 % Recall |
| Embedding dense | Ollama `qwen3-embedding:0.6b` (Matryoshka) | 1024d, lokal, multilingual |
| Embedding sparse | **FastEmbed BM25** (deutsch gestemmt) | Namen, Codes, Fachbegriffe |
| Vektor-DB | **Qdrant** — Named Vectors (dense+sparse) | **Hybrid Query API + RRF**, Payload-Indizes, Quantization |
| Reranker | **Logprobs-Reranker** (Ollama) | On-Prem |
| Confidence-Gate | Ampel (>0.7 / 0.4–0.7 / <0.4) | Anti-Halluzination Stufe 1 |
| LLM | Ollama `qwen3:14b` | Lokal (Uni-GPU), DSGVO-konform |
| Generierung | Anti-Halluzination + **Citation** + Grounding | URL-Whitelist + Source-IDs + Faithfulness |
| Streaming | **SSE Token-by-Token** | Default an |
| Memory | Window (5) + Summarization | Multi-Turn |
| API | FastAPI (Streaming, Lifespan, Health/Ready) | Rate-Limit |
| Frontend | Preact + Tailwind Widget (<100 KB) | Demonstrator-tauglich |
| Eval | Golden Q&A + **RAGAS** + Regression-CI | Recall@k/MRR + Faithfulness |
| Compliance | Lokal-first, **On-Prem-Default**, **EU AI Act Art. 4** | Audit-Log, DSGVO |
| Security | **Prompt-Injection-Abwehr**, RBAC, Secrets | Output-Filter, Rate-Limit |
| Observability | structlog + **OpenTelemetry** | Tracing über alle Stufen |
| Deployment | **Docker-Compose** (Qdrant+Ollama+API+Widget) | Uni-Infra / Hetzner |

---

## 3. Architektur

Fünf Pipeline-Schichten über **Protocol-Interfaces** (austauschbar), plus vier Querschnitts-Schichten.

```
┌──────────────────────────────────────────────────────────────┐
│ SCHICHT 5 · PRÄSENTATION   FastAPI (SSE) · Preact-Widget · UI │
│ SCHICHT 4 · GENERIERUNG    LLM · Prompts · Validation+Citation │
│                            Grounding · Guardrails · Memory     │
│ SCHICHT 3 · RETRIEVAL      Hybrid (Dense+Sparse) · RRF · MMR · │
│                            Router · Rerank · Confidence-Gate   │
│ SCHICHT 2 · INDEXIERUNG    HybridChunker · Splitter · Context- │
│                            Enricher · Embedder (dense+sparse)  │
│ SCHICHT 1 · DATEN          DOCLING (Rückgrat) · manual_loader ·│
│                            httpx (sekundär) · Boilerplate      │
└──────────────────────────────────────────────────────────────┘
   QUERSCHNITT:  EVAL (RAGAS) · COMPLIANCE (EU AI Act, DSGVO) ·
                 OBSERVABILITY (OTEL) · SECURITY (Prompt-Injection)
```

**Geschwister-Module (nach dem Spine, noch nicht im Repo):** `norm_store/` (deterministische
Schwellen, *nicht* vektorisiert) · `live_data/` (OPC-UA-Snapshot-Reader) · `agent/`
(Perceive → Check → RAG-Kontext → Lagebericht + Bestätigen/Verwerfen-Eval). Sie docken über
dieselben Protocols an, ohne den Spine zu ändern.

---

## 4. Verzeichnisstruktur

```
halle-gehirn/
├── CLAUDE.md · PLANNING.md · TASKS.md
├── pyproject.toml · ruff.toml · mypy.ini · .env.example
├── docker-compose.yml · Caddyfile · ecosystem.config.js   (Phase 10)
├── docs/taxonomie.md                  # Inhaltsmodell (Facetten + Vokabular)
├── data/
│   ├── vokabular.yaml                 # kontrolliertes Vokabular (Registry)
│   ├── manifest.yaml                  # Kurations-Metadaten je Dokument
│   ├── manual/{abschlussarbeiten,projektberichte,transfer,anlagen,transkripte}/
│   ├── raw/  ·  eval/
├── src/halle_gehirn/
│   ├── config.py                      # zentrale Config (liest .env)
│   ├── api/{main,schemas, routes/{chat,health,admin}}.py
│   ├── extraction/                    # ── DOCLING-RÜCKGRAT ──
│   │   ├── base · docling_extractor · html_extractor
│   │   ├── boilerplate · title_extractor · manual_loader
│   ├── scraper/{fetcher,js_fetcher}.py         # sekundär
│   ├── pipeline/
│   │   ├── protocols.py · orchestrator · factory · ingest
│   │   ├── chunker · sentence_splitter · context_enricher
│   │   └── stages/{confidence,validation,grounding,guardrails}.py
│   ├── embeddings/{provider,ollama_embedder,sparse_embedder,colbert_embedder,reranker}.py
│   ├── retrieval/{retriever,query_transform,router}.py
│   ├── vector_store/{qdrant_client,schema}.py  # schema.py = Qdrant + Taxonomie
│   ├── generator/{ollama_client,prompts,smalltalk,memory}.py
│   ├── eval/{golden_qa,metrics,runner}.py
│   ├── governance/{audit,consent,erasure}.py
│   ├── observability/{logging_config,tracing}.py
│   └── ui/streamlit_app.py
├── src/scripts/{initial_crawl,reindex,eval_queries,snapshot}.py
└── tests/
```

---

## 5. Inhaltsmodell & Qdrant-Schema

Das **Inhaltsmodell** ist der Kern dieses Projekts (siehe `docs/taxonomie.md`). Grundsatz:
**Facetten statt Ordner** — ein Chunk wird über orthogonale Metadaten beschrieben, die
„Verschachtelung" entsteht zur Abfragezeit über Filter-Kombinationen (Self-Querying).

Facetten (in `vector_store/schema.py` als Enums / Registry-Slugs, indiziert):
`bereich` (transfer/forschung/lehre/infrastruktur) · `thema` (die 3 Forschungsschwerpunkte) ·
`doc_type` · `quelltyp` (primaer/kuratiert/synthetisch — **Provenienz-Pflicht**) · `herkunft` ·
`anlage` · `projekt` · `ansprechperson` · `jahr` · `vertraulichkeit` · `status` · `grad`.

Kuration je Dokument über `data/manifest.yaml`; wachsende Facetten (`anlage`/`projekt`/
`ansprechperson`) sind Registry-validierte Slugs in `data/vokabular.yaml`. **`anlage`-Slugs
spiegeln die Geräte-IDs der Demonstrator-API** → verlustfreie Verzahnung mit der späteren
OPC-UA-Live-Schicht.

Qdrant: Collection `halle_wissen` mit Named Vectors (`dense` 1024 COSINE + `sparse` IDF),
ScalarQuantization(INT8), Payload-Indizes für alle Facetten. Hybrid-Query via Query API mit
`prefetch[dense, sparse]` → `FusionQuery(RRF)` → MMR → Rerank → Confidence-Gate.

---

## 6. Konfiguration

Alle Parameter in `.env` (Vorlage: `.env.example`), typisiert in `config.py`. Kernwerte:
`LLM_MODEL=qwen3:14b` · `EMBEDDING_MODEL=qwen3-embedding:0.6b` · `QDRANT_COLLECTION=halle_wissen` ·
`USE_CONTEXTUAL_RETRIEVAL=true` · `FUSION=rrf` · `CONF_GREEN=0.7`/`CONF_YELLOW=0.4` ·
`ON_PREM=true` · `BOT_NAME=Jarvis` · `PRIMARY_COLOR=<TODO BTU-Hausfarbe>`.

---

## 7. Kernprinzipien (gelten für alle Outputs)

1. **Lokal-first** — alles on-prem (Ollama + Qdrant + FastEmbed). Cloud nur optionaler Hybrid, nie Default.
2. **Modular über Protocols** — jede Stage implementiert ein `Protocol`; austauschbar. `factory.py` baut aus Config.
3. **Facetten statt Ordner** — eine Collection, flache Chunks + Metadaten; Struktur entsteht zur Abfragezeit.
4. **Provenienz-Pflicht** — `quelltyp` immer gesetzt; kein Beleg ohne Quelle. Synthetisches ≠ Primärquelle.
5. **Anti-Halluzination, mehrstufig** — Confidence-Gate → URL-Whitelist → Citation-Enforcement → Grounding-Check.
6. **Deutsch-optimiert** — Splitter, BM25-Stemming, Prompts, Smalltalk auf `de`.
7. **Compliance- & Audit-by-Design** — Audit-Log, On-Prem-Default, Right-to-Erasure, EU-AI-Act-Hooks von Anfang an.
8. **Eval-getrieben** — keine Stack-Änderung ohne Golden-Q&A-/RAGAS-Lauf; Regression grün.

---

## 8. Code-Standards

**Golden Rules:** KISS · YAGNI · DRY · **Fail Fast** (spezifische Exceptions früh, nie `except: pass`).

**Harte Limits:** Datei ≤ 300 Zeilen · Funktion ≤ 50 · Parameter ≤ 5 (sonst Dataclass/Config) · Verschachtelung ≤ 3 (Early Returns).

**Konventionen:** `snake_case` Files/Funktionen · `PascalCase` Klassen · `SCREAMING_SNAKE` Konstanten.
Immer: Type Hints, Google-Style-Docstrings, f-strings, `pathlib`, `structlog` statt `print`, Context Manager, async für I/O.

---

## 9. Claude-Code-Workflow

**Vor jeder Aufgabe:** `TASKS.md` (Prioritäten) + `PLANNING.md` (Architektur) lesen. Betroffene Schicht(en)/Protocol identifizieren. Bei Unklarheit zur Architektur: **fragen, nicht raten.**

**Erlaubt:** Files anlegen/lesen/ändern · `uv pip install` (dann `pyproject.toml` pflegen) · Tests/Linter/Dev-Server · Git commit/branch/diff (**kein** push).

**Verboten:** `rm -rf` auf breite Pfade · `.env` ändern (nur `.env.example`) · `git push` ohne Freigabe · Kern-Architektur ohne Rücksprache ändern · Cloud-Dienste als Default.

**Pre-Completion:** ruff+mypy grün · Type Hints + Docstrings · keine hardcodierten Pfade/Secrets · `pyproject.toml` gepflegt · Tests für neue Stage · `TASKS.md` aktualisiert · bei Retrieval-/Embedding-/Prompt-Änderung Eval-Lauf grün.

---

## 10. Build-Reihenfolge

Phasenweise (Phase 0 → 10) aus dem IkigAI RAG Prompt-Paket. Empfohlene Reihenfolge für den ersten Build:
**0 → 1 → 2 → 3 → 4 → 5 → 6 → 8 → 9 → 7 → 10** (Eval & Compliance vorgezogen — Demonstrator- und
Förder-Differenzierer). Detail-Backlog: TASKS.md. Danach die Geschwister-Module (Norm-Store, OPC-UA,
Agent) laut PLANNING.md.

**Status:** Phase 0 (Bootstrap) angelegt — Struktur, Config, Protocols, Taxonomie-Schema, Tooling, Docs.
