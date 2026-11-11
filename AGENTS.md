# AGENTS.md — Halle-Gehirn

> Arbeitsanweisung für AI-Coding-Agents. Kanonische Detailquelle: **`CLAUDE.md`** (Stack/Architektur),
> `docs/taxonomie.md` (Inhaltsmodell), `PLANNING.md` / `TASKS.md` (Roadmap/Backlog).
> Package: `halle_gehirn` · Collection: `halle_wissen` · Sprache: Code-Kommentare/Docs `de`, Antworten an Nutzer `de`.

## Projekt

Lokal-first, DSGVO-konformer RAG-Stack (Säule 1: Wissensbasis) für die Modellfabrik des Lehrstuhls
KI-gestützte Automatisierungstechnik (BTU Cottbus-Senftenberg). Bot-Anzeigename: **KI Fabrik Scout**.
Dokumente werden per Hybrid-Suche (dense + sparse) durchsuchbar; Antworten sind quellenbelegt mit
mehrstufiger Anti-Halluzination (Confidence-Ampel → URL-Whitelist → Citation → Grounding).
Alles läuft on-prem: Ollama + Qdrant + FastEmbed. **Keine Cloud-Dienste als Default.**

## Stack (kurz)

- Python 3.12 via `uv`, async, vollständige Type Hints.
- Extraction: **Docling** (Rückgrat), Trafilatura (reines HTML), httpx-Crawler nur sekundär.
- Chunking: Docling HybridChunker + deutscher Splitter; Contextual Retrieval default-an.
- Embeddings: Ollama `qwen3-embedding:0.6b` (dense 1024d) + FastEmbed BM25 (sparse).
- Vektor-DB: Qdrant, Named Vectors, Hybrid-Query (RRF) → MMR → Rerank → Confidence-Gate.
- LLM: Ollama `qwen3` (lokal). API: FastAPI (SSE-Streaming). Frontends: Preact/Vite.
- Eval: Golden Q&A + RAGAS. Observability: structlog + OpenTelemetry.

## Verzeichnisse

- `src/halle_gehirn/` — Kern: `api/`, `extraction/`, `embeddings/`, `vector_store/`, `eval/`, `observability/`, `config.py`.
- `src/scripts/` — Operative Skripte (`reindex`, `full_reingest`, `eval_*`, …).
- `scripts/` — Diagnose-/Hilfsskripte. `tests/` — pytest-Suite.
- `data/` — `manifest.yaml` (Kuration je Dokument), `vokabular.yaml` (Registry-Slugs), `manual/<sorte>/`, `eval/`.
- `frontend/jarvis-widget/` (Chat, Port 3000) · `frontend/jarvis-wissensbestand/` (Admin, Port 3001).

## Befehle

```bash
uv sync                                  # Abhängigkeiten
uv run ruff check .                      # Lint
uv run mypy src                          # Typen
uv run pytest                            # Tests
uv run python -m src.scripts.reindex     # Re-Indexierung
scripts/start_all.ps1                    # Alle Dev-Dienste (API 8001, 3000, 3001)
```

- Vor Offline/CI: `python scripts/cache_tiktoken.py` (tiktoken-Encoding `cl100k_base`).
- Ports sind kanonisch: 3000 Chat, 3001 Wissensbestand, 8001 API, 5001 Docling Serve, 6335 Qdrant, 11434 Ollama. Vite-Server nutzen `strictPort: true` — nie still auf anderen Port ausweichen.

## Kernprinzipien

1. **Lokal-first** — on-prem ist Default; Cloud nur optionaler Hybrid nach Rücksprache.
2. **Modular über Protocols** — jede Pipeline-Stage implementiert ein `Protocol`; Austausch über `factory.py` + Config.
3. **Facetten statt Ordner** — eine Qdrant-Collection, flache Chunks + Metadaten-Facetten; Struktur zur Abfragezeit via Filter.
4. **Provenienz-Pflicht** — Facette `quelltyp` (primaer/kuratiert/synthetisch) immer gesetzt; kein Beleg ohne Quelle.
5. **Anti-Halluzination, mehrstufig** — Confidence-Gate (0.7/0.4) → URL-Whitelist → Citation-Enforcement → Grounding-Check.
6. **Deutsch-optimiert** — Splitter, BM25-Stemming, Prompts, Smalltalk auf `de`.
7. **Compliance-by-Design** — Audit-Log, DSGVO, EU AI Act Art. 4, Right-to-Erasure.
8. **Eval-getrieben** — keine Retrieval-/Embedding-/Prompt-Änderung ohne grünen Golden-Q&A-Lauf.

## Code-Standards

- Golden Rules: KISS · YAGNI · DRY · **Fail Fast** (spezifische Exceptions früh, nie `except: pass`).
- Harte Limits: Datei ≤ 300 Zeilen · Funktion ≤ 50 · Parameter ≤ 5 (sonst Dataclass/Config) · Verschachtelung ≤ 3 (Early Returns).
- Konventionen: `snake_case` Dateien/Funktionen, `PascalCase` Klassen, `SCREAMING_SNAKE` Konstanten.
- Immer: Type Hints, Google-Style-Docstrings, f-strings, `pathlib`, `structlog` statt `print`, Context Manager, async für I/O.
- Keine hardcodierten Pfade oder Secrets. Konfiguration ausschließlich über `.env` (Vorlage `.env.example`), typisiert in `config.py`.

## Workflow-Regeln

- **Vor jeder Aufgabe:** `TASKS.md` (Prioritäten) und `PLANNING.md` lesen; betroffene Schicht/Protocol identifizieren. Bei Architektur-Unklarheit: **fragen, nicht raten.**
- **Erlaubt:** Dateien anlegen/lesen/ändern · `uv`-Install (dann `pyproject.toml` pflegen) · Tests/Linter/Dev-Server · Git commit/branch/diff.
- **Verboten:** `rm -rf` auf breite Pfade · `.env` ändern (nur `.env.example`) · `git push` ohne Freigabe · Kern-Architektur ohne Rücksprache ändern · Cloud als Default.
- **Vor Abschluss:** ruff + mypy grün · Tests grün (neue Stage hat Tests) · `pyproject.toml` gepflegt · `TASKS.md` aktualisiert · bei Retrieval/Embedding/Prompt-Änderung: Eval-Lauf grün.

## Daten hinzufügen

1. Quelldokument nach `data/manual/<sorte>/` (abschlussarbeiten, projektberichte, transfer, anlagen, transkripte).
2. Eintrag in `data/manifest.yaml` (Kurations-Metadaten gemäß `docs/taxonomie.md`).
3. Neue Maschinen/Projekte/Personen als Slugs in `data/vokabular.yaml` registrieren (`anlage`-Slugs = Geräte-IDs der Demonstrator-API).
4. `uv run python -m src.scripts.reindex`.

## Deprecated

Streamlit-Ingest-Tool (`ui/ingest_app.py`) ist **deprecated** und ersetzt durch das
Wissensbestand-Frontend (Port 3001, `/admin/wissen`-API). Nicht erweitern, nicht referenzieren.
