# Halle-Gehirn

Lokal-first, DSGVO-konformer **RAG-Stack** für die Modellfabrik des Lehrstuhls *KI-gestützte
Automatisierungstechnik* (BTU Cottbus-Senftenberg). Dieses Repo ist **Stufe 1 / Säule 1** des
Gesamtsystems Halle-Gehirn: die Wissensbasis. Bot-Anzeigename: **KI Fabrik Scout**.

Dokumente (Berichte, Abschlussarbeiten, Handbücher, Anlagendoku, kuratiertes Erfahrungswissen)
werden per Hybrid-Suche (dense + sparse) durchsuchbar; Antworten sind quellenbelegt, mit exakten
Verweisen und mehrstufiger Anti-Halluzination (Confidence-Ampel → URL-Whitelist → Citation →
Grounding). Alles läuft on-prem (Ollama + Qdrant + FastEmbed).

## Kanon-Dokumente

- **`CLAUDE.md`** — Stack- und Architektur-Definition (Claude Code liest sie zu Beginn jeder Aufgabe).
- **`docs/taxonomie.md`** — das Inhaltsmodell (Facetten, Payload-Schema, kontrolliertes Vokabular).
- **`PLANNING.md`** / **`TASKS.md`** — Roadmap und Backlog je Phase.

## Setup

Voraussetzungen: Python 3.12, [`uv`](https://docs.astral.sh/uv/), lokal laufendes Ollama + Qdrant.

```bash
# Abhängigkeiten
uv sync

# Konfiguration
cp .env.example .env      # Werte prüfen (PRIMARY_COLOR = BTU-Hausfarbe eintragen)

# Qualität
uv run ruff check .
uv run mypy src
uv run pytest
```

> **Offline/CI-Hinweis:** Der Chunker lädt beim Import das tiktoken-Encoding
> `cl100k_base` (einmaliger Netz-Download). In Umgebungen ohne Egress vorher
> `python scripts/cache_tiktoken.py` ausführen — legt die Datei unter
> `.tiktoken_cache/` ab, `conftest.py` nutzt sie dann automatisch.

## Daten hinzufügen

1. Quelldokumente nach `data/manual/<sorte>/` legen (abschlussarbeiten, projektberichte, transfer,
   anlagen, transkripte).
2. Je Dokument einen Eintrag in `data/manifest.yaml` (Kurations-Metadaten — siehe `docs/taxonomie.md`).
3. Neue Maschinen/Projekte/Personen als Slugs in `data/vokabular.yaml` registrieren.
4. `uv run python -m scripts.reindex` (ab Phase 2).

## Status

Phase 0 (Bootstrap) angelegt: Struktur, Config, Protocols, Taxonomie-Schema, Tooling, Docs.
Nächster Schritt: Phase 1 (Docling-Extraction). Backlog in `TASKS.md`.

## Kontext

Teil des Vorhabens „Agentische KI für die Modellfabrik". Die weiteren Bausteine (deterministischer
Norm-Store, OPC-UA-Live-Daten, agentischer Lage-Loop) folgen als Geschwister-Module nach dem Spine
(siehe `PLANNING.md`). Betrieben im Rahmen des Mittelstand-Digital Zentrums Spreeland.
