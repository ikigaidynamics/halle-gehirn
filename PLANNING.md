# PLANNING.md — Halle-Gehirn

Architektur-Kurzfassung und Roadmap. Detail-Backlog: `TASKS.md`. Kanon: `CLAUDE.md`.

## Wo dieses Repo steht

Halle-Gehirn ist das agentische System für die Modellfabrik (Lehrstuhl KI-gestützte
Automatisierungstechnik, BTU Cottbus-Senftenberg). **Dieses Repo = Stufe 1 / Säule 1: die
Wissensbasis** (RAG-Spine). Es liefert schon für sich das „Werkzeug gegen den Wissensverlust"
und ist der vorführbare Demonstrator-Kern.

## Architektur in einem Absatz

Fünf Pipeline-Schichten (Daten → Indexierung → Retrieval → Generierung → Präsentation) über
Protocol-Interfaces, plus Querschnitt (Eval, Compliance, Observability, Security). Docling ist das
Extraction-Rückgrat, Hybrid Search (dense+sparse, RRF) der Retrieval-Standard, Qdrant die Vektor-DB,
Ollama (qwen3) LLM + Embeddings — alles lokal. Anti-Halluzination mehrstufig: Confidence-Gate →
URL-Whitelist → Citation → Grounding. Inhaltlich trägt das Ganze die **Facetten-Taxonomie**
(`docs/taxonomie.md`): eine Collection `halle_wissen`, flache Chunks + Metadaten, Struktur zur
Abfragezeit via Self-Querying.

## Roadmap — Spine (dieses Repo)

Phasen 0–10 (siehe TASKS.md), Reihenfolge **0→1→2→3→4→5→6→8→9→7→10**. Ziel: lauffähige,
evaluierbare, vorzeigbare Wissensbasis — „Jarvis 1.0".

## Roadmap zum Gesamtsystem (Geschwister-Module, NACH dem Spine)

Bewusst **noch nicht** im Repo — erst wenn der Spine steht, als protokoll-modulare Siblings:

1. **`norm_store/` — deterministischer Norm-Store.** Exakte Schwellen, *nicht* im Vektorraum. Das
   Urteil über Zahlen trifft nachvollziehbarer Code, nicht das LLM. Interface über Function-Calling.
2. **`live_data/` — OPC-UA-Snapshot-Reader.** Strukturierter Hallenzustand zum Auswertezeitpunkt.
   `anlage`-Slugs der Wissensbasis = Geräte-IDs der Demonstrator-API → verlustfreier Join.
3. **`agent/` — Perceive-Judge-Report-Loop.** wahrnimmt → prüft gegen Normen → zieht RAG-Kontext →
   quellenbelegter Lagebericht. Plus operative **Bestätigen/Verwerfen-Eval** (Fachpersonen bestätigen/
   verwerfen jede Bewertung → Prüfdatensatz baut sich selbst auf).

Prinzip: Siblings docken über dieselben Protocols an, ohne den Spine zu verändern. Keine
verfrühten Stubs — die Zielstruktur steht hier dokumentiert, damit nichts verloren geht.

## Offene Eingaben

- **BTU-Hausfarbe** (`PRIMARY_COLOR`) — Platzhalter, für Widget/Branding nachzutragen.
- **`anlage`-Vokabular** — vorläufig in `data/vokabular.yaml`; gegen die Demonstrator-API-Geräte-IDs
  abgleichen und exakt übernehmen.
- **Startdokumente** — vom Lehrstuhlserver in `data/manual/` legen, im `manifest.yaml` eintragen.
