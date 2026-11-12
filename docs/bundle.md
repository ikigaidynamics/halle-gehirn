# Standalone-Bundle (portable App)

Das Halle-Gehirn wird als **portabler Ordner** (ZIP) ausgeliefert — ohne Python-,
Node- oder pip-Installation auf dem Ziel-PC. Basis: PyInstaller **onedir**.

## Aufbau des Bundles

```
halle-gehirn-app/
├── halle-gehirn.exe      # FastAPI-App (gefroren), startet Uvicorn auf Port 8001
├── _internal/            # Python-Runtime + Abhaengigkeiten (gefroren)
├── static/
│   ├── chat/             # Preact-Chat-SPA  (Vite-Build, base "/")
│   └── admin/            # Wissensbestand-SPA (Vite-Build, base "/admin/")
├── data/                 # manifest.yaml, vokabular.yaml, manual/, figures/, eval/
├── caches/
│   ├── tiktoken/         # cl100k_base-Encoding offline vorgewaermt
│   └── fastembed/        # Qdrant/bm25 (deutsch) offline vorgewaermt
├── logs/retrieval/
├── .env                  # Konfiguration (externen Dienste EINTRAGEN!)
├── env.beispiel
├── start.cmd             # Startskript (doppelklickbar)
└── README.md
```

## Externe Dienste (Ziel-PC)

Das Bundle enthaelt **keine** Modelle und **keine** Datenbanken. Erforderlich
sind vier Dienste; LLM und Embeddings wahlweise **Ollama** oder eine
**OpenAI-kompatible API** (vLLM, TEI, llama.cpp, echter OpenAI-Dienst …).

**Variante A — Ollama (Default):**

| Dienst         | Setting            | Beispiel                       |
|----------------|--------------------|--------------------------------|
| Ollama (LLM)   | `LLM_BACKEND=ollama`, `OLLAMA_URL` | `http://141.43.76.22:11434` |
| Ollama (Embed) | `EMBEDDING_BACKEND=ollama` | qwen3-embedding:0.6b   |
| Qdrant         | `QDRANT_URL`       | `http://141.43.76.22:6335`     |
| Docling Serve  | `DOCLING_SERVE_URL`| `http://141.43.76.21:5001`     |

**Variante B — OpenAI-kompatible API:**

| Dienst               | Setting            | Beispiel                       |
|----------------------|--------------------|--------------------------------|
| LLM (OpenAI-API)     | `LLM_BACKEND=openai`, `OPENAI_BASE_URL` | `http://141.43.76.22:8080/v1` |
| OpenAI (LLM-Modell)  | `OPENAI_MODEL` (leer = `LLM_MODEL`) | z.B. `qwen3-14b` |
| Embeddings (OpenAI-API) | `EMBEDDING_BACKEND=openai`, `EMBEDDING_OPENAI_BASE_URL` | `http://141.43.76.22:8081/v1` |
| OpenAI (Embed-Modell)| `EMBEDDING_OPENAI_MODEL` (leer = `EMBEDDING_MODEL`) | z.B. `qwen3-embedding-0.6b` |
| Qdrant               | `QDRANT_URL`       | `http://141.43.76.22:6335`     |
| Docling Serve        | `DOCLING_SERVE_URL`| `http://141.43.76.21:5001`     |

API-Schluessel (falls der Server Auth erwartet): `OPENAI_API_KEY` bzw.
`EMBEDDING_OPENAI_API_KEY` — leer fuer lokale Server ohne Auth. Die
Embedding-Dimension muss zu `EMBEDDING_DIM` (und damit zum Qdrant-Index)
passen. Die Backends sind unabhaengig waehlbar (z.B. LLM via OpenAI-API,
Embeddings via Ollama). Im Bundle sind beide Backends enthalten
(OpenAI-Clients nutzen httpx, keine zusaetzliche Runtime noetig);
geprueft per Smoke-Test gegen einen OpenAI-Stub.

Docling laeuft im Bundle-Betrieb **ausschliesslich** als externer Dienst
(Docling Serve, `POST /v1/convert/file`). Die Docling-Bibliothek ist bewusst
nicht im Bundle enthalten (Lazy-Import + PyInstaller-Excludes). Ist
`DOCLING_SERVE_URL` leer, scheitert die Extraktion fail-fast mit
Konfigurations-Hinweis.

## Build (Entwickler-PC)

Voraussetzungen: `.venv` mit dev-Extras (`pip install -e ".[dev]"`), Node + npm.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_bundle.ps1
```

Ablauf:
1. Vite-Builds beider Frontends (`base "/"` bzw. `"/admin/"`).
2. `pyinstaller bundle/pyinstaller.spec` (onedir; `collect_all` ohne
   Dependency-Closure; Excludes: docling, pymupdf, ragas, datasets, streamlit,
   playwright, torch, pyarrow, pandas, scipy, babel, sqlalchemy).
3. Zusammenstellung `dist/halle-gehirn-app/` (Exe, static/, data/, vorgewaermte
   caches/, .env, start.cmd, README).
4. `Compress-Archive` → `dist/halle-gehirn-app.zip` (~170 MB).

## Betrieb auf dem Ziel-PC

1. ZIP entpacken (beliebiger Ort, keine Installation).
2. `.env` pruefen: Adressen der externen Dienste eintragen.
3. `start.cmd` ausfuehren → Chat `http://localhost:8001/`,
   Admin `http://localhost:8001/admin/`.
4. Diagnose: `http://localhost:8001/ready` zeigt Qdrant-Erreichbarkeit und den
   aktiven LLM-Backend (Ollama `/api/tags` bzw. OpenAI `/v1/models`).

Hinweise: SmartScreen/AV-Ausnahme kann beim ersten Start noetig sein
(nicht signierte EXE). Der Ordner muss beschreibbar sein (`.env`, `data/`,
`logs/`, `caches/`).

## Wichtige Implementierungs-Eckpunkte

- `src/halle_gehirn/bundle/entrypoint.py`: setzt CWD = EXE-Verzeichnis
  (pydantic-settings findet `.env`), definiert `TIKTOKEN_CACHE_DIR`,
  `DATA_GYM_CACHE_DIR`, `FASTEMBED_CACHE_PATH` unter `caches/`, startet Uvicorn.
- `api/main.py` `_mount_static()`: bei gesetztem `STATIC_DIR` Mount `/admin`
  (Admin-SPA) und `/` (Chat-SPA); API-Routen sind zuerst registriert und
  gewinnen gegen die SPA-Mounts.
- `extraction/docling_extractor.py`: Docling nur lazy importiert;
  `TYPE_CHECKING`-Guard; API-Import laedt kein docling/pymupdf/ragas
  (Import-Audit: `heavy modules loaded: []`).
- `pyproject.toml`: Kern-Dependencies ohne docling/pymupdf4llm/ragas/datasets;
  Extras `ingest` und `eval` fuer den DEVELOP-Betrieb.
