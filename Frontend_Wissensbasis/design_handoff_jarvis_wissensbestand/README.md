# Handoff: Jarvis — Wissensbestand (Ingester / Dokumentenverwaltung & Indexierung, MDZ-Branding)

## Overview
Frontend für das **Ingest-Tool** von **Jarvis** (Repo `halle-gehirn`) — die Verwaltung des
Wissensbestands der Modellfabrik: Dokumente hochladen, Manifest-Metadaten kuratieren, Chunks in
Qdrant inspizieren und (neu) indexieren. **Hell**, im Branding des **Mittelstand-Digital Zentrums
Spreeland** (Weiß/Rot) — **identisches Designsystem** wie das Chat-Frontend (`design_handoff_jarvis_frontend`).

Es ersetzt/veredelt die bestehende Streamlit-App `src/halle_gehirn/ui/ingest_app.py`
(4 Tabs + Ollama-Sidebar).

Layout: **Topbar** oben · **Body** = `Sidebar (Ollama-Server + Collection-Stats, 266px)` + `Main`
(Tab-Bar + Tab-Inhalt) · **Förder-Fußzeile** unten.

## About the Design Files
`Jarvis Wissensbestand.dc.html` ist eine **Design-Referenz in HTML** (Prototyp), **kein**
Produktionscode. Die vorhandene App ist **Streamlit** (`streamlit`, `pandas`) — Ziel ist, dieses
Design **im Streamlit-Tool umzusetzen** (Custom-CSS via `st.markdown(unsafe_allow_html=True)` /
`st.set_page_config`, ggf. `st.tabs`, Theming über `.streamlit/config.toml`), **oder** — falls das
Demonstrator-Widget (Phase 7, Preact + Tailwind) auch die Kuration abdecken soll — als Preact-Komponenten.
Empfehlung: beim bestehenden **Streamlit** bleiben und nur Optik/Struktur angleichen; die Logik
(`manifest/editor.py`, `pipeline/ingest.py`, `pipeline/indexer.py`, `vector_store/qdrant_client.py`) bleibt.

Die Tabs im Prototyp sind **klickbar** (JS-State) — nur zur Demonstration der vier Ansichten.

## Fidelity
**High-fidelity (hifi).** Finale Farben, Typografie, Abstände, Radien, Zustände. Inhalte
(Dokumente, Chunks, Werte) sind realistische Platzhalter aus `data/manifest.yaml` /
`data/vokabular.yaml`; real kommen sie aus Manifest + Qdrant.

## Screens / Views
Eine App mit **4 Tabs** (entspricht `st.tabs([...])` in `ingest_app.py`).

### Gemeinsame Chrome
- **Topbar** (Höhe 64px, BG `#ffffff`, `border-bottom rgba(0,0,0,0.08)`): MDZ-Icon
  (`assets/MDZ_Icon.jpg`, 36×36, `radius:9px`) + Titel **„Jarvis — Wissensbestand"** (Inter 16px/700)
  + Untertitel „Dokumentenverwaltung & Indexierung · Mittelstand-Digital Zentrum Spreeland“ (11.5px, `#8a877f`).
  Rechts: On-Prem-Badge (grün), DSGVO-Chip, Avatar „RJ“.
- **Sidebar** (266px, BG `#faf9f6`, `border-right`): 
  - **Ollama-Server** (entspricht `_server_selector.py`): aktive Zeile „localhost:11434“ mit grünem
    Punkt + „online“ + ▾ (BG `#fff`, Border, 38px); darunter Offline-Server „gpu-node-02:11434“
    grau (grauer Punkt, „offline“).
  - **Collection-Card**: Zeilen Name = `halle_wissen` (rot, Mono), Dokumente = 4, Chunks = 218,
    Embedding = `qwen3:0.6b` (BG `#fff`, Border, `radius:11px`, Trennlinien).
  - **Lokal-first-Hinweis** unten (rot-soft Box).
- **Tab-Bar** (BG `#fff`, `border-bottom`): 4 Buttons „Bestand · Neues Dokument · Dokument-Viewer ·
  Indexieren“, `padding:15px 16px 13px`, 13.5px/600. Aktiv: Text `#E2001A` + `border-bottom:2px solid #E2001A`.
  Inaktiv: Text `#6b6963` + transparenter Border. (Nur diese zwei Style-Props wechseln mit dem State.)
- **Förder-Fußzeile** (58px, BG `#f3f2ef`): links Spreeland-Logo (34px) + Text, rechts BMWK-Logo (40px).

### Tab 1 — Bestand  (`_bestand_tab.py`)
- **Gespeicherte Dokumente** (Manifest): Titelzeile + „4 Dokumente“. Liste von Karten (BG `#fff`,
  Border, `radius:11px`, `padding:13px 15px`): **Status-Punkt** (grün = in Qdrant indexiert /
  grau `#c9c6bf` = nicht), Titel (13.5px/600) + `datei`-Slug (Mono, `#a09d95`), Caption
  „doc_type · bereich · vertraulichkeit“, rechts **„Entfernen“**-Button (Outline). 
  Legende mit grünem/grauem Punkt (statt Emoji-Ampeln — bewusst monochrom).
- **Indexierte Dokumente** (Qdrant): „3 Dokumente mit 218 Chunks“; **Tabelle** mit Spalten
  Datei · Titel · Chunks · Hash · Manifest (Header BG `#faf9f6`, Mono-Uppercase-Labels, Zeilen
  mit Trennlinie). „Im Manifest: Ja“ grün. Waisen-Warnung (orphans) als Warn-Box, wenn vorhanden.

### Tab 2 — Neues Dokument  (`ingest_app._render_neu_tab` + `_neu_tab_helpers.py`)
- **Upload-Dropzone**: gestrichelter roter Rahmen (`1.5px dashed rgba(226,0,26,0.3)`,
  BG `rgba(226,0,26,0.03)`), Upload-Icon (Lucide, rot), Text „Datei hierher ziehen oder wählen“ +
  „PDF, DOCX, PPTX, XLSX, Markdown oder TXT“, roter „Durchsuchen“-Button.
- **Auto-Erkennung-Hinweis** (grün): „<datei> analysiert — Metadaten automatisch vorausgefüllt“.
- **Metadaten** (2-Spalten-Grid, Labels 11.5px/600, `*` = Pflicht rot): Titel · Dokumenttyp ·
  Bereich (Multiselect-Chips, rot) · Herkunft · Quelltyp | Vertraulichkeit · Status · Jahr · Grad.
  Selectbox = 38px-Box mit ▾; Multiselect = Chip-Box.
- **Facetten (optional)**: Anlage · Thema · Ansprechperson · Projekt (Multiselect-Chips; Chips
  zeigen den **Slug** in Mono, z. B. `predictive_maintenance ✕`).
- **„Neuen Facetten-Wert anlegen“**-Expander (BG `#faf9f6`).
- Divider + roter **„Dokument speichern“**-Button.

### Tab 3 — Dokument-Viewer  (`_dokument_tab.py`)
- **Dokument-Auswahl** (Selectbox, zeigt Titel + `(datei)`).
- **Manifest-Metadaten** (Card BG `#faf9f6`, 3-Spalten-Grid): Titel/Typ/Herkunft/Quelltyp/Status/
  Bereich/Vertraulichkeit/Grad/Jahr — menschenlesbar (`resolve_label`).
- **Chunks in Qdrant** („78 Chunks indexiert“): Liste aufklappbarer Chunk-Karten. Label
  „Chunk N | X Zeichen | ID: …“ (Mono). Aufgeklappt:
  - **Text**-Box (BG `#f8f9fa`, `border-left:3px solid #E2001A`) — im Original blau `#0066cc`,
    hier auf **Rot** umgestellt (Branding).
  - **Context-Prefix**-Box (BG `#fff8e6`, Border `rgba(227,160,8,0.3)`, kursiv, amber).
  - **Metadaten-Tabelle** (Grid `120px 1fr`, Label-Spalte BG `#f3f2ef`).
  - Aktionen: **Löschen** / **Bearbeiten** (Outline-Buttons).

### Tab 4 — Indexieren  (`_indexieren_tab.py`)
- Titel + Caption. Buttons **Alle / Keine / Nur neue auswählen** (letzterer rot-soft).
- **Dokument-Checkboxen** je Zeile: Checkbox (an = rot mit ✓) + Status-Punkt (grün/grau) + Titel +
  `datei`-Slug + Status-Label „indexiert/neu“. Ausgewählte/neue Zeile rot-soft hervorgehoben.
- **Auswahl-Info** (rot-soft Box): „1 Dokument ausgewählt — 1 neu“.
- **„Collection zurücksetzen“**-Checkbox (+ Warnhinweis).
- Roter **„Indexieren starten“**-Button.
- **Ergebniszustand**: grüne Erfolgsleiste „44 Chunks in Qdrant geschrieben“; **5 Metrik-Kacheln**
  (Gesamt/Erfolgreich/Übersprungen/Fehlgeschlagen = weiß; Chunks = rot-soft), Werte Mono 22px/700
  (Erfolgreich grün, Chunks rot). **Log-Block** dunkel (`#1c1c1c`, Mono, INFO grün, DONE amber).

## Interactions & Behavior
- **Tabs**: State `tab` ∈ {bestand, neu, viewer, index}; Button-Klick wechselt Ansicht. (In Streamlit
  über `st.tabs` bereits gegeben.)
- **Upload → Auto-Detect**: `metadata_detector.detect_metadata` füllt das Formular vor (Hinweis-Box),
  danach editierbar.
- **Speichern**: `validate_entry` → `save_uploaded_file` → `save_manifest_entry`.
- **Entfernen** (Bestand): `delete_manifest_entry(datei)`.
- **Indexieren**: optional `reset_collection()` → `run_ingest(selected_dateien)` (Extract+Chunk) →
  `embed_and_upsert(payloads)`; Stats-Kacheln + Live-Logs.
- **Chunk bearbeiten/löschen**: `update_point_payload` / `delete_points_by_ids` (Hinweis:
  Embedding bleibt bis zur Neu-Indexierung unverändert).
- **Ollama-Server**: Health-Check per `GET {url}/api/tags`; online/offline-Label; Auswahl in
  Session-State.
- **Hover**: Buttons abdunkeln (Rot-Hover `#b30015`).
- **Responsive**: unter ~1000px Sidebar zusammenklappen; Tabelle horizontal scrollen.

## State Management
- `tab` (aktive Ansicht).
- Upload: `_meta_suggestion`, `_detected_filename`, `_form_version` (wie im Streamlit-Code).
- Auswahl Indexieren: `idx_<datei>` Booleans; `do_reset`.
- Chunk-Edit: `editing_<point_id>`.
- Server: `active_ollama_url`.
- Datenquellen: Manifest (`list/load_manifest_entries`), Qdrant (`list_indexed_documents`,
  `get_chunks_by_datei`).

## Design Tokens
- **Farben**: Primär-Rot `#E2001A`; Rot-Hover `#b30015`; Rot-Soft-BG `rgba(226,0,26,0.03–0.10)`;
  Rot-Border `rgba(226,0,26,0.14–0.30)`.
- **Status/Ampel**: grün `#2f9e44` (indexiert/Erfolg); grau `#c9c6bf` (nicht indexiert); amber
  `#e3a008` / Box `#fff8e6` (Context-Prefix).
- **Neutral**: Seite `#ecebe8`; Weiß `#ffffff`; Panel-Grau `#faf9f6`/`#f7f6f3`/`#f3f2ef`/`#f0eeea`;
  Chunk-Text-BG `#f8f9fa`; Log-BG `#1c1c1c`; Text `#1a1a1a`/`#2a2a2a`/`#333`; sekundär
  `#555`/`#6b6963`/`#8a877f`/`#9a978f`/`#a09d95`; Border `rgba(0,0,0,0.05–0.12)`.
- **Typografie**: **Inter** (400–800) UI; **JetBrains Mono** (400–600) für Slugs/Dateinamen/Hashes/
  IDs/Metrik-Zahlen/Logs. Größen: Body 12–14px, Tab 13.5px, H2 17px, Metrik 22px.
- **Radius**: Inputs/Buttons 8–10px; Karten/Boxen 10–12px; Chips 6px.
- **Shadow**: Rot-CTA `0 6px 18px -6px rgba(226,0,26,0.6)`; Frame `0 40px 110px -35px rgba(30,20,20,0.4)`.

## Assets
- `assets/MDZ_Icon.jpg` — App-Icon (im Repo auch `public/MD_Icon_bg.jpg`).
- `assets/MD_zentrum_Spreeland.png` — Zentrum-Logo (Fußzeile). SVG: `public/MD_zentrum_Spreeland_RGB.svg`.
- `assets/Mittelstand-Digital-BMWK.png` — BMWK-Förderlogo (Fußzeile).
- Icons: Lucide-Style Stroke-Icons (Upload). Fonts On-Prem hosten (DSGVO), nicht von Google laden.
- Original-Streamlit nutzt Emojis (🟢/⚪) für Status — hier bewusst durch **monochrome Punkte** ersetzt.

## Files
- `Jarvis Wissensbestand.dc.html` — vollständiger Prototyp (alle Styles inline, 4 klickbare Tabs).
- Repo-Referenzen `halle-gehirn`: `src/halle_gehirn/ui/ingest_app.py`, `ui/_bestand_tab.py`,
  `ui/_dokument_tab.py`, `ui/_indexieren_tab.py`, `ui/_neu_tab_helpers.py`, `ui/_server_selector.py`,
  `ui/_display_helpers.py`; `manifest/editor.py`; `data/manifest.yaml` & `data/vokabular.yaml`;
  `docs/taxonomie.md`.
- Passt zum Chat-Handoff `design_handoff_jarvis_frontend/` — gleiche Tokens/Fonts/Assets.
