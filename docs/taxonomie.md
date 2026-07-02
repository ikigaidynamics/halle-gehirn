# Taxonomie & Payload-Schema — `halle_wissen` (Säule 1)

**Projekt:** Halle-Gehirn · Lehrstuhl Automatisierungstechnik (LS AT) · Wissensbasis
**Zweck:** Kanonische Struktur- und Metadaten-Definition für die RAG-Wissensbasis. Erweitert das Payload-Schema aus `CLAUDE.md` (Kap. 5) um die domänenspezifischen Facetten des Lehrstuhls. Diese Datei ist die Referenz für `vector_store/schema.py` und für die Kuration jedes Dokuments.

---

## Leitgedanke

> **Struktur vorziehen, Inhalt klein starten.** Das *vollständige* Schema wird jetzt festgelegt — damit später keine Re-Ingestion nötig ist. *Befüllt* wird inkrementell: Ein Flyer lässt `anlage` und `projekt` einfach leer. So bekommst du beides: den kleinen Start (2–3 Dokumentsorten) **und** eine Struktur, die von Tag 1 alle wichtigen Felder kennt.

---

## 1. Grundprinzipien

1. **Facetten statt Ordner.** Transfer / Forschung / Lehre / Infrastruktur sind eine gute *Landkarte*, aber ein schlechter *Ordnerbaum* — dieselbe Maschine, Person oder Arbeit gehört meist zu mehreren Bereichen. Deshalb werden sie zu **mehrwertigen Metadaten-Tags**, nicht zu einem Verzeichnispfad.
2. **Eine Collection.** Alles liegt in `halle_wissen`. „Maschine" ist ein *Feld* (`anlage`), keine eigene Collection. Übergreifende Fragen funktionieren, kein Fan-out nötig. Fragmentierung in Per-Maschine-Collections wäre verfrüht.
3. **Kontrolliertes Vokabular.** Filter und Self-Querying funktionieren nur bei einer *kleinen, festen* Werteliste je Facette. Keine freien Keywords — sonst driftet „Robotik" vs. „robotik" vs. „Greifroboter".
4. **Provenienz-Pflicht.** `quelltyp` ist immer gesetzt und unterscheidet Primärquelle / kuratiert / synthetisch. Das speist Confidence-Ampel und Zitate — eine KI-Zusammenfassung ist kein Handbuch.
5. **Trennung Format ↔ Bedeutung.** `source_type` = *technisches* Format (pdf/docx/…), `doc_type` = *semantische* Dokumentsorte (abschlussarbeit/flyer/…). Zwei verschiedene Felder.
6. **Stabile IDs & Delta.** Deterministische IDs aus `(source_hash, chunk_index)` (wie CLAUDE.md) → idempotente Re-Ingestion und Right-to-Erasure über `source_hash`.

---

## 2. Von deiner Skizze zum Modell

Deine Handskizze bleibt vollständig erhalten — sie wird nur von einem *Baum* zu *Facetten-Werten* übersetzt. Jeder Ast wird ein Metadaten-Wert:

| In der Skizze | Wird zur Facette | Werte |
|---|---|---|
| `LS AT` / „alles Wissen" | die Collection selbst | `halle_wissen` (Default-Owner `herkunft = lehrstuhl_at`) |
| Transfer · Forschung · Lehre · Infrastruktur | **`bereich`** (mehrwertig) | `transfer` · `forschung` · `lehre` · `infrastruktur` |
| MDZ · EDIH · BTU | **`herkunft`** | `mdz` · `edih` · `btu` · `lehrstuhl_at` · `extern` |
| Flyer · Online-Beitrag · Workshop-Slides · Projektbericht · Promotion · MA/BA · Anlagendoku | **`doc_type`** | siehe §4 |
| Projekte (Direct, Lufo) | **`projekt`** (mehrwertig) | `direct` · `lufo` · … |
| Greifroboter · Predictive-Maintenance-Maschine | **`anlage`** (mehrwertig) | `greifroboter` · `predictive_maintenance` · … |

**Die „Verschachtelung" verschwindet aus dem Speicher und entsteht neu zur Abfragezeit.** Statt fest verdrahteter Hierarchie kombinierst du Facetten: „Forschungsergebnisse zum Greifroboter aus 2024" = `bereich=forschung AND anlage=greifroboter AND jahr>=2024`. Wird die erste Struktur schlecht, änderst du Vokabular-Werte — nicht den Speicherbaum.

---

## 3. Payload-Schema — vollständig

Zwei Klassen von Feldern. **Auto-Felder** füllt die Pipeline; **Kurations-Felder** legst du pro Dokument fest — *das* ist die eigentliche Taxonomie-Arbeit.

### 3.1 Auto-Felder (Pipeline füllt sie)

| Feld | Typ | Beschreibung |
|---|---|---|
| `text` | str | Finaler Chunk-Text (inkl. Contextual-Präfix) → wird embedded |
| `text_raw` | str | Original-Chunk ohne Präfix (Anzeige/Zitat) |
| `context_prefix` | str? | Vom Contextual-Enricher erzeugter Kontextsatz |
| `source_url` | str? | Quelle (Datei-Pfad oder URL) |
| `source_type` | str | **Technisches Format:** `pdf`·`docx`·`pptx`·`html`·`manual`·`transcript`·`audio` |
| `lang` | str | Sprache, Default `de` |
| `page` | int? | Seitenzahl (bei paginierten Quellen) |
| `table_ref` | str? | Referenz auf Tabellen-Chunk |
| `chunk_index` | int | Position im Dokument |
| `char_start`/`char_end` | int | Zeichen-Offsets im Originaldokument |
| `ingested_at` | str | ISO-Zeitstempel der Ingestion |
| `source_hash` | str | Hash der Quelle → Delta-Crawl + Right-to-Erasure |

### 3.2 Kurations-Felder (du legst sie je Dokument fest)

| Feld | Typ | Index | Pflicht | Beschreibung |
|---|---|---|---|---|
| `titel` | str | — | **Pflicht** | Aussagekräftiger Titel (generische ersetzen) |
| `breadcrumb` | str? | — | optional | Herkunfts-/Navigationspfad |
| `doc_type` | Enum | ✅ KEYWORD | **Pflicht** | Semantische Dokumentsorte (§4) |
| `bereich` | list\[Enum\] | ✅ KEYWORD | **Pflicht** | Ein oder mehrere: transfer/forschung/lehre/infrastruktur |
| `quelltyp` | Enum | ✅ KEYWORD | **Pflicht** | primaer / kuratiert / synthetisch (§5) |
| `herkunft` | Enum | ✅ KEYWORD | **Pflicht** | Produzierende Einheit / Ownership |
| `jahr` | int? | ✅ INTEGER | empfohlen | Erscheinungs-/Bearbeitungsjahr |
| `anlage` | list\[str\] | ✅ KEYWORD | leer erlaubt | Zugehörige Maschine(n)/Asset(s), Registry-Slug |
| `projekt` | list\[str\] | ✅ KEYWORD | leer erlaubt | Benanntes Forschungs-/Entwicklungsvorhaben, Registry-Slug |
| `ansprechperson` | list\[str\] | ✅ KEYWORD | leer erlaubt | Autor/Kontakt, Registry-Slug |
| `vertraulichkeit` | Enum | ✅ KEYWORD | Default `intern` | Zugriffs-/Governance-Stufe (vorgezogen) |
| `status` | Enum | ✅ KEYWORD | Default `final` | final / in_arbeit (z. B. WIP-Promotion) |
| `grad` | Enum? | ✅ KEYWORD | nur Abschlussarbeit | bachelor / master |

> **`herkunft` vs. `projekt` — die eine Regel, die Verwechslung vermeidet:** `herkunft` = *wer hat es gemacht* (Ownership/Vertrauen: MDZ, EDIH, Lehrstuhl, extern). `projekt` = *zu welchem benannten Vorhaben gehört der Inhalt* (Direct, Lufo). MDZ/EDIH sind Einheiten/Programme → `herkunft`, nicht `projekt`.

---

## 4. Kontrollierte Vokabulare

Die geschlossenen Facetten (Enums) — bewusst klein halten, nur mit Absicht erweitern.

### `bereich` — die „Dreifaltigkeit" + Infrastruktur (mehrwertig)
| Wert | Bedeutung |
|---|---|
| `transfer` | Wissenstransfer in Wirtschaft/Öffentlichkeit (MDZ, EDIH, Flyer, Workshops) |
| `forschung` | Wissenschaftliche Vorhaben & Ergebnisse (Projekte, Projektberichte, Promotionen) |
| `lehre` | Ausbildung (Abschlussarbeiten, Lehrbücher, Lehrmaterial) |
| `infrastruktur` | Anlagen, Maschinen, Betriebsmittel des Lehrstuhls |

### `doc_type` — semantische Dokumentsorte (einwertig)
| Wert | Bedeutung |
|---|---|
| `abschlussarbeit` | Bachelor-/Masterarbeit (Grad via `grad`) |
| `promotion` | Dissertation (auch WIP via `status=in_arbeit`) |
| `projektbericht` | Projektergebnis/-bericht (oft lang, 100+ S.) |
| `anlagendoku` | Lehrstuhl-eigene Anlagendokumentation |
| `handbuch` | Hersteller-Maschinenhandbuch |
| `flyer` | Transfer-Flyer |
| `online_beitrag` | Web-/Blog-Beitrag |
| `workshop_slides` | Workshop-/Foliensammlung |
| `lehrbuch` | Lehrbuch (z. B. Berger) |
| `experten_transkript` | Transkribiertes Experten-Interview (kuratiert) |
| `video_transkript` | Transkript aus der Videosammlung |
| `zusammenfassung` | Verdichtete Übersichts-/Zusammenfassungsversion |
| `sonstiges` | Auffangwert (sparsam nutzen) |

### `quelltyp` — Provenienz / Vertrauensstufe (einwertig)
| Wert | Bedeutung |
|---|---|
| `primaer` | Originaldokument (Handbuch, Bericht, Arbeit, Flyer) — höchste Belegkraft |
| `kuratiert` | Von Menschen aufbereitet (Experten-Transkript, redigierte Notizen) |
| `synthetisch` | KI-generiert (z. B. Zusammenfassung aus der Online-Präsenz) — nachrangig zitieren |

### `herkunft` — Ownership / produzierende Einheit (einwertig)
| Wert | Bedeutung |
|---|---|
| `lehrstuhl_at` | Lehrstuhl Automatisierungstechnik (Default) |
| `mdz` | Mittelstand-Digital Zentrum |
| `edih` | European Digital Innovation Hub |
| `btu` | BTU (übergeordnet, außerhalb LS AT) |
| `extern` | Externe Quelle (z. B. Hersteller-Handbuch) |

### `vertraulichkeit` — Governance (einwertig, Default `intern`)
| Wert | Bedeutung |
|---|---|
| `offen` | Darf öffentlich zitiert werden (Flyer, publizierte Beiträge) |
| `intern` | Nur intern (Standard für die meisten Lehrstuhl-Dokumente) |
| `vertraulich` | Sensibel (WIP-Promotionen, unpublizierte Ergebnisse) |

### `status` (einwertig, Default `final`) · `grad` (nur `abschlussarbeit`)
`status`: `final` · `in_arbeit`  |  `grad`: `bachelor` · `master`

### Wachsende Facetten — `anlage` · `projekt` · `ansprechperson`
Diese wachsen mit dem Bestand und sind daher **keine Enums**, sondern **Registry-validierte Slugs** (eine `data/vokabular.yaml`, s. §10). Konvention: `snake_case`, ein kanonischer Slug je Entität.
- `anlage`: `greifroboter` · `predictive_maintenance` · …
- `projekt`: `direct` · `lufo` · …
- `ansprechperson`: `bork` · `berger` · … (Nachname klein; bei Namensgleichheit `nachname_vorname`)

---

## 5. Provenienz-Pflicht (warum `quelltyp` zentral ist)

Das Halle-Konzept fordert „kein Hinweis ohne Quelle". `quelltyp` macht das im Payload operativ:
- **Zitate & Ampel** können synthetische Inhalte kennzeichnen bzw. abwerten — eine KI-Zusammenfassung darf nicht wie ein Handbuch als harter Beleg auftreten.
- **Das Experten-Transkript** („Martin, 10 Min. das Wichtigste") ist das *kuratierte Erfahrungswissen* des Konzepts → `quelltyp=kuratiert`, `doc_type=experten_transkript`. Nicht als Handbuch verbuchen.
- **Synthetische 20-Seiten-Zusammenfassungen** aus der Online-Präsenz sind erlaubt und nützlich → `quelltyp=synthetisch`, sichtbar getrennt vom Original.

Faustregel: Wenn ein Chunk primär auf einer KI-Erzeugung beruht → `synthetisch`. Wenn ein Mensch ihn aufbereitet/geprüft hat → `kuratiert`. Sonst → `primaer`.

---

## 6. Zuordnung in der Praxis — das Manifest

Die Kurations-Felder hängen über eine **Sidecar-Datei** an den Quelldateien: `data/manifest.yaml`. `pipeline/ingest.py` liest das Manifest und schreibt die Felder ins Payload. So bleibt die Zuordnung versionierbar und getrennt vom Dokument.

```yaml
# data/manifest.yaml — Kurations-Metadaten je Quelldokument
dokumente:
  - datei: "abschlussarbeiten/2024_mustermann_greifroboter.pdf"
    titel: "Bahnplanung für den Greifroboter unter Störeinflüssen"
    doc_type: abschlussarbeit
    grad: master
    bereich: [lehre, forschung]
    anlage: [greifroboter]
    projekt: [direct]
    ansprechperson: [mustermann, bork]
    jahr: 2024
    herkunft: lehrstuhl_at
    quelltyp: primaer
    vertraulichkeit: intern
    status: final

  - datei: "transfer/mdz_flyer_ki-mittelstand.pdf"
    titel: "KI im Mittelstand — MDZ-Flyer"
    doc_type: flyer
    bereich: [transfer]
    herkunft: mdz
    jahr: 2025
    quelltyp: primaer
    vertraulichkeit: offen
    # anlage / projekt / ansprechperson: leer → weglassen
```

**Ordnerstruktur der Quelldateien** (rein kosmetisch, für Menschen — die Wahrheit steht im Manifest):

```
data/
├── manifest.yaml
├── vokabular.yaml            # Registry: erlaubte anlage/projekt/ansprechperson
├── raw/                      # gecrawlte/rohe Quellen
└── manual/
    ├── abschlussarbeiten/
    ├── projektberichte/
    ├── transfer/             # Flyer, Online-Beiträge, Workshop-Slides
    ├── anlagen/              # Handbücher, Anlagendoku
    └── transkripte/          # Experten-/Video-Transkripte
```

---

## 7. Beispiele (vollständige Payloads)

**① Masterarbeit** — gehört zu Lehre *und* Forschung, maschinenbezogen:
`doc_type=abschlussarbeit` · `grad=master` · `bereich=[lehre, forschung]` · `anlage=[greifroboter]` · `projekt=[direct]` · `ansprechperson=[mustermann, bork]` · `jahr=2024` · `herkunft=lehrstuhl_at` · `quelltyp=primaer` · `vertraulichkeit=intern`

**② MDZ-Flyer** — reiner Transfer, öffentlich:
`doc_type=flyer` · `bereich=[transfer]` · `herkunft=mdz` · `jahr=2025` · `quelltyp=primaer` · `vertraulichkeit=offen` · `anlage=[]` · `projekt=[]`

**③ Hersteller-Handbuch Predictive-Maintenance-Maschine** — Infrastruktur, extern:
`doc_type=handbuch` · `bereich=[infrastruktur]` · `anlage=[predictive_maintenance]` · `herkunft=extern` · `quelltyp=primaer` · `vertraulichkeit=intern`

**④ Experten-Transkript zur PM-Maschine** — kuratiertes Erfahrungswissen:
`doc_type=experten_transkript` · `bereich=[infrastruktur, forschung]` · `anlage=[predictive_maintenance]` · `ansprechperson=[martin]` · `herkunft=lehrstuhl_at` · `quelltyp=kuratiert` · `jahr=2026`

**⑤ KI-Zusammenfassung der Lehrstuhl-Forschungsschwerpunkte** — synthetisch:
`doc_type=zusammenfassung` · `bereich=[forschung, transfer]` · `herkunft=lehrstuhl_at` · `quelltyp=synthetisch` · `vertraulichkeit=offen`

---

## 8. `schema.py`-Fragment (drop-in fürs Repo)

```python
"""Payload-Schema & Vokabular für halle_wissen. Erweitert CLAUDE.md Kap. 5."""
from enum import Enum
from pydantic import BaseModel, Field


# ── Geschlossene Facetten (kontrolliertes Vokabular) ──
class Bereich(str, Enum):
    TRANSFER = "transfer"
    FORSCHUNG = "forschung"
    LEHRE = "lehre"
    INFRASTRUKTUR = "infrastruktur"

class DocType(str, Enum):
    ABSCHLUSSARBEIT = "abschlussarbeit"
    PROMOTION = "promotion"
    PROJEKTBERICHT = "projektbericht"
    ANLAGENDOKU = "anlagendoku"
    HANDBUCH = "handbuch"
    FLYER = "flyer"
    ONLINE_BEITRAG = "online_beitrag"
    WORKSHOP_SLIDES = "workshop_slides"
    LEHRBUCH = "lehrbuch"
    EXPERTEN_TRANSKRIPT = "experten_transkript"
    VIDEO_TRANSKRIPT = "video_transkript"
    ZUSAMMENFASSUNG = "zusammenfassung"
    SONSTIGES = "sonstiges"

class Quelltyp(str, Enum):
    PRIMAER = "primaer"
    KURATIERT = "kuratiert"
    SYNTHETISCH = "synthetisch"

class Herkunft(str, Enum):
    LEHRSTUHL_AT = "lehrstuhl_at"
    MDZ = "mdz"
    EDIH = "edih"
    BTU = "btu"
    EXTERN = "extern"

class Vertraulichkeit(str, Enum):
    OFFEN = "offen"
    INTERN = "intern"
    VERTRAULICH = "vertraulich"

class Grad(str, Enum):
    BACHELOR = "bachelor"
    MASTER = "master"

class Status(str, Enum):
    FINAL = "final"
    IN_ARBEIT = "in_arbeit"


class ChunkPayload(BaseModel):
    """Vollständiges Payload je Chunk. Auto-Felder füllt die Pipeline,
    Kurations-Felder kommen aus data/manifest.yaml."""
    # — Inhalt (Auto) —
    text: str
    text_raw: str
    context_prefix: str | None = None
    # — Technik/Herkunft (Auto) —
    source_url: str | None = None
    source_type: str                      # pdf|docx|pptx|html|manual|transcript|audio
    lang: str = "de"
    page: int | None = None
    table_ref: str | None = None
    chunk_index: int
    char_start: int
    char_end: int
    ingested_at: str
    source_hash: str
    # — Titel/Navigation —
    titel: str
    breadcrumb: str | None = None
    # — Semantische Facetten (Kuration, indiziert) —
    doc_type: DocType
    bereich: list[Bereich]
    quelltyp: Quelltyp
    herkunft: Herkunft
    jahr: int | None = None
    anlage: list[str] = Field(default_factory=list)          # Registry-Slugs
    projekt: list[str] = Field(default_factory=list)         # Registry-Slugs
    ansprechperson: list[str] = Field(default_factory=list)  # Registry-Slugs
    # — Governance (vorgezogen) —
    vertraulichkeit: Vertraulichkeit = Vertraulichkeit.INTERN
    status: Status = Status.FINAL
    grad: Grad | None = None              # nur bei doc_type == ABSCHLUSSARBEIT


# ── Payload-Indizes (gefilterte Suche + Self-Querying) ──
from qdrant_client import QdrantClient
from qdrant_client.models import PayloadSchemaType

KEYWORD_FELDER = (
    "doc_type", "bereich", "quelltyp", "herkunft",
    "anlage", "projekt", "ansprechperson",
    "vertraulichkeit", "status", "grad", "lang", "source_type",
)

def create_payload_indices(client: QdrantClient, collection: str = "halle_wissen") -> None:
    """Legt alle Payload-Indizes an. KEYWORD-Index matcht auch Array-Felder."""
    for feld in KEYWORD_FELDER:
        client.create_payload_index(collection, feld, PayloadSchemaType.KEYWORD)
    client.create_payload_index(collection, "jahr", PayloadSchemaType.INTEGER)
```

> Die Listen-Felder (`bereich`, `anlage`, `projekt`, `ansprechperson`) werden mit `PayloadSchemaType.KEYWORD` indiziert — Qdrant matcht dann auf *jedes* Array-Element (`bereich` enthält `forschung`).

---

## 9. Startmenge — die konkreten ersten drei

Wähle 2–3 `doc_type`s, die (a) schon als saubere PDFs vorliegen, (b) *verschiedene* `bereich`e abdecken (damit du die Facetten testest) und (c) mindestens eine maschinenbezogene Sorte enthalten (damit du `anlage` testest):

| # | `doc_type` | deckt `bereich` ab | testet |
|---|---|---|---|
| 1 | `abschlussarbeit` (MABA) | lehre, forschung | Mehrfach-`bereich`, `grad`, `ansprechperson` |
| 2 | `flyer` + `online_beitrag` (MDZ) | transfer | `herkunft=mdz`, `vertraulichkeit=offen` |
| 3 | `anlagendoku` / `handbuch` | infrastruktur | `anlage`, `herkunft=extern` |

15–30 PDFs, ins Manifest eintragen, `halle_wissen` befüllen → **Jarvis 1.0.** Läuft das gut, kommen weitere `doc_type`s dazu, ohne dass sich am Schema etwas ändert.

---

## 10. Vokabular-Pflege & Erweiterung

- **`data/vokabular.yaml`** hält die erlaubten Slugs der wachsenden Facetten. `ingest.py` validiert `anlage`/`projekt`/`ansprechperson` dagegen und bricht bei unbekanntem Slug ab (Fail-Fast gegen Tippfehler/Drift):

```yaml
anlage:
  greifroboter:        "Greifroboter (Halle, Station 3)"
  predictive_maintenance: "Predictive-Maintenance-Prüfstand"
projekt:
  direct: "DIRECT — Forschungsprojekt"
  lufo:   "LuFo — Luftfahrtforschung (Bork)"
ansprechperson:
  bork:   "Christian Bork"
  berger: "Prof. Berger"
```

- **Erweitern = append-only.** Neue Werte ergänzen, bestehende nicht umbenennen (sonst brechen Filter). Muss ein Slug weg, per Re-Ingestion des betroffenen Dokuments.
- **Enums erweitern** nur mit Bedacht — jeder neue `doc_type`/`bereich` ist eine Modellentscheidung, keine spontane Notiz.
- **Metadaten schlagen Ordner.** Verschiebst du Quelldateien, ändert sich nichts an der Taxonomie — es zählt allein das Manifest.

---

*Diese Datei ist die kanonische Taxonomie-Referenz für `halle_wissen`. Änderungen am Vokabular oder Schema hier dokumentieren, bevor sie in `schema.py` / `manifest.yaml` landen.*
