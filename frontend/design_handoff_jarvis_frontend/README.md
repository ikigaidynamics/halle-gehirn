# Handoff: Jarvis — Halle-Gehirn Wissensbasis (Chat/Search-Frontend, MDZ-Branding)

## Overview
Frontend für **Jarvis**, den quellenbelegten RAG-Chat der Wissensbasis der Modellfabrik
(Repo `halle-gehirn`, Säule 1). Es ist ein **helles** Chat-/Such-Interface im Branding des
**Mittelstand-Digital Zentrums Spreeland** (Weiß/Rot). Kernidee: jede Antwort ist
quellenbelegt, die Confidence wird als Ampel gezeigt, und der ausgewählte Beleg wird rechts
im **Beleg-Inspektor** mit vollständigem Chunk, Metadaten und mehrstufiger
Anti-Halluzinations-Kette angezeigt. Läuft lokal (On-Prem, DSGVO, EU-AI-Act).

Layout (3 Spalten): **Slim-Icon-Rail** (links) · **Konversation** (Mitte) · **Beleg-Inspektor** (rechts),
darunter eine **Förder-Fußzeile**. Darüber eine **Topbar**.

## About the Design Files
Die Datei `Jarvis Wissensbasis.dc.html` in diesem Bundle ist eine **Design-Referenz in HTML** —
ein Prototyp, der Aussehen und Verhalten zeigt, **kein** direkt zu kopierender Produktionscode.
Aufgabe ist, dieses Design im **bestehenden Stack von `halle-gehirn` nachzubauen**: laut
`CLAUDE.md` ein **Preact + Tailwind-Widget (< 100 KB), demonstrator-tauglich**, angebunden an die
FastAPI-**SSE**-Endpunkte. Nutzt die etablierten Muster/Bibliotheken des Repos. Die HTML nutzt
Inline-Styles (Prototyp-Zwang) — im echten Code als saubere Preact-Komponenten + Tailwind-Klassen
umsetzen.

Die Datei ist eine `.dc.html` (Design-Component-Prototyp). Für eine reine Vorschau im Browser
kann sie so geöffnet werden; für die Implementierung zählt die Struktur, nicht das Dateiformat.

## Fidelity
**High-fidelity (hifi).** Finale Farben, Typografie, Abstände, Radien und Zustände sind final.
UI pixelgenau mit den Bibliotheken/Patterns des Repos nachbauen. Inhalte (Fragen, Antworten,
Dokument) sind realistische Platzhalter aus `data/manifest.yaml` / `docs/taxonomie.md` und kommen
später aus der API.

## Screens / Views

### Screen: Jarvis Chat (Single View, 3-spaltig)
- **Purpose**: Nutzer stellt Fragen zur Modellfabrik; erhält quellenbelegte Antworten mit
  Confidence-Ampel; prüft Belege im rechten Inspektor.
- **Layout**: Vollhöhen-Container (Prototyp fix 1360×868, real fluid/responsive), Spalten:
  `Topbar (Höhe 60px)` oben; darunter `Body` als Flex-Row mit drei Spalten:
  `Rail (66px, fix)` · `Konversation (flex:1, min-width:0)` · `Inspektor (400px, fix)`;
  ganz unten `Förder-Fußzeile (58px)`. Alle Spalten scrollen unabhängig.

#### Komponente: Topbar
- Höhe 60px, Hintergrund `#ffffff`, `border-bottom: 1px solid rgba(0,0,0,0.08)`, `padding: 0 22px`.
- **Links**: MDZ-Icon (`assets/MDZ_Icon.jpg`, 34×34, `border-radius:9px`) + Wortmarke **„Jarvis"**
  (Inter 16px/700, `#1a1a1a`, `letter-spacing:-0.01em`). *(Kein Untertitel, kein
  Collection-Selector — wurde bewusst entfernt.)*
- **Rechts** (Flex, `gap:10px`): 
  - **On-Prem-Badge**: grüner Punkt (`#2f9e44`, Glow) + Text „On-Prem · qwen3:8b“ (JetBrains Mono 11px/500, `#2f9e44`), BG `rgba(47,158,68,0.08)`, Border `rgba(47,158,68,0.28)`, `padding:7px 11px`, `radius:8px`.
  - **Chips** „DSGVO“ und „EU AI Act“: BG `#f5f4f1`, Border `rgba(0,0,0,0.08)`, Text `#555` 11px/600, `radius:8px`.
  - **Avatar** „RJ“: 36×36, `radius:10px`, BG `#f0eeea`, Border `rgba(0,0,0,0.08)`, Text `#555` 12px/700.

#### Komponente: Slim-Icon-Rail (links, 66px)
- Hintergrund `#faf9f6`, `border-right:1px solid rgba(0,0,0,0.07)`, vertikale Flex, `gap:6px`, `padding:16px 0`, zentriert.
- **Neu-Button** (oben): 42×42, `radius:12px`, BG `#E2001A`, weißes „+“ 21px, Shadow `0 6px 16px -6px rgba(226,0,26,0.6)`.
- **Icons** (Lucide-Style, Stroke, 19×19, `stroke-width:1.8`):
  - **Chat** (aktiv): Icon `#E2001A`, BG `rgba(226,0,26,0.1)`, Border `rgba(226,0,26,0.25)`, 42×42, `radius:12px`.
  - **Dokumente** (file), **Statistik** (bar-chart), **Einstellungen** (gear, unten via `margin-top:auto`): Icon `#a09d95`, transparent.
- **Keine Emojis** — ausschließlich monochrome Strich-Icons (bewusste Vorgabe).

#### Komponente: Konversation (Mitte)
- Hintergrund `#f7f6f3`; Scrollbereich `padding:30px 26px 8px`; innerer Inhalt `max-width:660px; margin:0 auto`; Nachrichten in Spalte mit `gap:22px`.
- **User-Bubble** (rechtsbündig, `flex-direction:row-reverse`): Avatar „RJ“ 30×30 (`radius:9px`, BG `#f0eeea`, Border `rgba(0,0,0,0.08)`); Bubble BG `rgba(226,0,26,0.08)`, Border `rgba(226,0,26,0.2)`, Text `#222` 14px/1.6, `radius:15px` mit `border-top-right-radius:5px`, `padding:11px 15px`.
- **Assistant-Message** (linksbündig): Jarvis-Avatar = MDZ-Icon 30×30 (`radius:9px`, `box-shadow:0 0 0 1px rgba(226,0,26,0.25)`).
  - **Confidence-Ampel** (über der Bubble): drei Punkte (grün `#2f9e44` aktiv, gelb `rgba(227,160,8,.28)`, rot `rgba(240,96,58,.28)` gedimmt) + Text „Hohe Konfidenz · 0.82“ (11.5px/600, `#2f9e44`). BG `rgba(47,158,68,0.09)`, Border `rgba(47,158,68,0.28)`, `radius:8px`, `padding:5px 11px`, `width:fit-content`. Bei mittlerer Konfidenz: gelber Punkt aktiv, Text/Farbe `#e3a008`.
  - **Antwort-Bubble**: BG `#ffffff`, Border `rgba(0,0,0,0.08)`, `radius:14px` mit `border-top-left-radius:5px`, `padding:15px 17px`, Text `#333` 14px/1.72, `box-shadow:0 1px 2px rgba(0,0,0,0.03)`. Fettbegriffe `#111`/600.
  - **Zitat-Marker** (inline, hochgestellt): runde Buttons 18×18, `radius:50%`, JetBrains Mono 10px/600. Aktiv/primär: BG `#E2001A`, Text `#fff`. Sekundär: BG `rgba(226,0,26,0.14)`, Text `#E2001A`.
  - **Beleg-Zähler** (Footer der Bubble): oben `border-top:1px solid rgba(0,0,0,0.07)`, Text „2 Belege“ (JetBrains Mono 10px/500, `#9a978f`).
  - **Streaming-State**: blinkender Caret am Textende — `inline-block; width:2px; height:15px; background:#E2001A; animation: blink 1s step-end infinite`.
- **Composer** (unten, sticky im Konversations-Container): `border-top:1px solid rgba(0,0,0,0.07)`, BG `#f7f6f3`, `padding:14px 26px 18px`; Eingabezeile `max-width:660px; margin:0 auto`, BG `#ffffff`, Border `rgba(0,0,0,0.12)`, `radius:15px`, `padding:10px 12px`: links Attach-Quadrat 30×30 (`#f0eeea`, „＋“), Platzhalter „Folgefrage stellen…“ (`#9a978f` 14px), rechts Send-Button 36×36 (`radius:10px`, BG `#E2001A`, „↑“). Untertext zentriert JetBrains Mono 10.5px/500 `#a09d95`: „Multi-Turn-Kontext (Fenster 5) · quellenbelegt · On-Prem · keine Cloud“.

#### Komponente: Beleg-Inspektor (rechts, 400px)
- Hintergrund `#ffffff`, `border-left:1px solid rgba(0,0,0,0.08)`, scrollbar.
- **Header** (sticky, BG `#ffffff`, `border-bottom`): links „BELEG-INSPEKTOR“ (JetBrains Mono 10px/600, `letter-spacing:0.16em`, uppercase, `#9a978f`); rechts roter Kreis „1“ 18×18 + „ausgewählt“.
- **Dokument-Karte**: Icon-Kachel 40×40 (`radius:10px`, BG `rgba(226,0,26,0.1)`, roter file-text-Stroke-Icon 20×20) + Titel (14px/600, `#161616`, `line-height:1.4`) + Pfad/Autor (JetBrains Mono 10px/500, `#a09d95`): „manual/abschlussarbeiten/ · Khaled Abdalla“.
- **Metadaten-Tabelle** („Facetten · Metadaten“): Card BG `#faf9f6`, Border `rgba(0,0,0,0.08)`, `radius:12px`. Grid `132px 1fr`, Zeilen mit `border-top:1px solid rgba(0,0,0,0.06)`, `padding:8px 13px`. **Wichtig: Labels & Werte menschenlesbar/deutsch anzeigen; die Backend-Slugs bleiben in den Daten unverändert.** Mapping siehe unten. Label `#8a877f` 11.5px/500, Wert `#2a2a2a` 11.5px/600; **Bereich** und **Anlage** in Rot `#E2001A`; **Quelltyp** als grünes Badge „Primärquelle“ (BG `rgba(47,158,68,0.12)`, `#2f9e44`).
- **Chunk (vollständig)**: Header „Chunk · vollständig“ + rechts Meta „S. 47 · char 12480–13120 · #chunk 38“ (JetBrains Mono, `#a09d95`/`#b8b5ad`). Box: BG `rgba(226,0,26,0.04)`, Border `rgba(226,0,26,0.15)`, `border-left:3px solid #E2001A`, `radius:11px`, `padding:14px 15px`; Text `#3a3a3a` 12.5px/1.7. **Der komplette Chunk wird ohne Kürzung angezeigt** (bewusste Vorgabe). Darunter `context_prefix`-Zeile (JetBrains Mono 10px, `#a09d95`).
- **Anti-Halluzination · mehrstufig**: 4 Zeilen-Karten (BG `#faf9f6`, Border `rgba(0,0,0,0.07)`, `radius:10px`, `padding:10px 12px`), je grüner ✓-Kreis 18×18 (`rgba(47,158,68,0.15)`/`#2f9e44`) + Label (`#3a3a3a` 12px) + Wert (JetBrains Mono 11px/600): 
  1. **Confidence-Gate** → „0.82 · grün“ (`#2f9e44`)
  2. **Citation-Enforcement** → „2/2 belegt“ (`#8a877f`)
  3. **Grounding · Faithfulness** → „0.91“ (`#2f9e44`)
  4. **Quelle-Whitelist** → „lehrstuhl_at“ (`#8a877f`)
- **„Quelle öffnen ↗“**-Button: volle Breite, 42px, BG `#E2001A`, Text `#fff` 13px/600, `radius:11px`, Shadow.

#### Komponente: Förder-Fußzeile
- Höhe 58px, BG `#f3f2ef`, `border-top:1px solid rgba(0,0,0,0.08)`, `padding:0 24px`, `justify-content:space-between`.
- Links: Zentrum-Spreeland-Logo (`assets/MD_zentrum_Spreeland.png`, Höhe 34px) + Text „Ein Angebot des Mittelstand-Digital Zentrums Spreeland“ (11px, `#777`).
- Rechts: BMWK-Förderlogo (`assets/Mittelstand-Digital-BMWK.png`, Höhe 40px).
- Fußzeile bewusst **hell** (Logos sind schwarz-auf-transparent).

## Deutsche Anzeige der Metadaten (Frontend-Mapping — Slugs bleiben im Backend)
| Feld (Slug)      | Label (Anzeige)      | Wert-Slug                              | Wert (Anzeige)                        |
|------------------|----------------------|----------------------------------------|----------------------------------------|
| doc_type         | Dokumententyp        | abschlussarbeit                        | Abschlussarbeit                        |
| grad             | Grad                 | master                                 | Master                                 |
| bereich          | Bereich              | forschung, infrastruktur, transfer     | Forschung, Infrastruktur, Transfer     |
| anlage           | Anlage               | predictive_maintenance                 | Predictive Maintenance                 |
| thema            | Thema                | mensch_maschine_interaktion            | Mensch-Maschine-Interaktion            |
| ansprechperson   | Ansprechperson       | berger, lautsch                        | Prof. Berger, M. Lautsch               |
| jahr             | Jahr                 | 2025                                   | 2025                                   |
| herkunft         | Herkunft             | lehrstuhl_at                           | Lehrstuhl Automatisierungstechnik      |
| quelltyp         | Quelltyp             | primaer                                | Primärquelle (grünes Badge)            |
| vertraulichkeit  | Vertraulichkeit      | offen                                  | Offen                                  |
| status           | Status               | final                                  | Final                                  |

Empfehlung: Zentrales Mapping-Objekt (Label-Dictionary je Facette) im Frontend, das die Slugs aus
`docs/taxonomie.md` / `data/vokabular.yaml` in Anzeigetexte übersetzt. Die API liefert weiterhin
Slugs; nur die Darstellung wird lokalisiert.

## Interactions & Behavior
- **Frage senden**: POST an FastAPI-Query-Endpunkt; Antwort **token-by-token via SSE** streamen; während des Streamens blinkender Caret; danach Ampel + Zitat-Marker + Beleg-Zähler einblenden.
- **Zitat-Marker klick** (① ② …): setzt den zugehörigen Beleg als „ausgewählt“ und füllt den Beleg-Inspektor (Dokument-Karte, Metadaten, vollständiger Chunk, Anti-Halluzination). Aktiver Marker = rot gefüllt, andere = rot-soft.
- **Ampel**: Farbe/Text aus dem Confidence-Score (grün ≥ 0.7, gelb 0.4–0.7, rot < 0.4 — Schwellen aus `CLAUDE.md` `CONF_GREEN`/`CONF_YELLOW`).
- **Rail**: Neu-Anfrage (+) startet leeren Thread; Icons wechseln Ansicht (Chat/Dokumente/Statistik/Einstellungen).
- **„Quelle öffnen“**: öffnet das Originaldokument (Datei/Deep-Link).
- **Hover**: Buttons leicht abdunkeln (Rot-Hover ≈ `#b30015`); Karten dezenter Shadow.
- **Responsive**: unter ~1100px Inspektor als Overlay/Drawer (statt fixe 3. Spalte); Rail ggf. zusammenklappen; Konversation behält `max-width:660px`.

## State Management
- `messages`: Liste `{ role: 'user'|'assistant', content, sources[], confidence, grounding }`.
- `streaming`: bool + laufender Text-Puffer (SSE).
- `selectedSourceId`: aktueller Beleg für den Inspektor.
- `conversationId` + Verlauf; Multi-Turn-Fenster = 5 (Memory, siehe `CLAUDE.md`).
- Datenabruf: Query/SSE, Transcript/Chunk-Detail, Health (`/api/health`) für den On-Prem-Badge.

## Design Tokens
- **Farben**: Primär-Rot `#E2001A`; Rot-Hover `#b30015`; Rot-Soft-BG `rgba(226,0,26,0.08)`; Rot-Border `rgba(226,0,26,0.2–0.25)`; Chunk-BG `rgba(226,0,26,0.04)`.
- **Ampel**: grün `#2f9e44`, gelb `#e3a008`, rot `#f0603a`.
- **Neutral**: Seite `#ecebe8`; App/Weiß `#ffffff`; Panel-Grau `#faf9f6` / `#f7f6f3` / `#f5f4f1` / `#f3f2ef` / `#f0eeea`; Text `#1a1a1a`/`#2a2a2a`/`#333`; sekundär `#555`/`#8a877f`/`#9a978f`/`#a09d95`; Border `rgba(0,0,0,0.06–0.12)`.
- **Typografie**: **Inter** (400/500/600/700/800) für UI; **JetBrains Mono** (400/500/600) für Meta/Labels/Werte/Badges. Größen: Body 14px, Meta 10–12px, Titel 16px.
- **Radius**: Buttons/Icons 8–12px; Bubbles 14–15px (mit 5px an der Sprecher-Ecke); Karten 10–12px; Pill 50%.
- **Shadow**: Rot-CTA `0 6px 18px -6px rgba(226,0,26,0.6)`; Karten `0 1px 2px rgba(0,0,0,0.03)`; Frame `0 40px 110px -35px rgba(30,20,20,0.4)`.
- **Keyframes**: `blink` (Caret), `tpulse` (Typing-Dots).

## Assets
- `assets/MDZ_Icon.jpg` — MDZ-App-Icon (rotes Platinen-Symbol), genutzt als App-Logo **und** Jarvis-Avatar.
- `assets/MD_zentrum_Spreeland.png` — Logo „Mittelstand-Digital Zentrum Spreeland“ (Fußzeile). Original auch als SVG im Repo `halle-gehirn/public/MD_zentrum_Spreeland_RGB.svg`.
- `assets/Mittelstand-Digital-BMWK.png` — BMWK-Förderlogo-Lockup (Fußzeile).
- Icons: Lucide-Style Stroke-Icons (chat, file, bar-chart, gear, file-text) — im echten Code `lucide-preact` o. ä. verwenden.
- Fonts: Google Fonts (Inter, JetBrains Mono) — im Repo On-Prem selbst hosten (DSGVO), nicht von Google laden.

## Files
- `Jarvis Wissensbasis.dc.html` — der vollständige HTML-Prototyp (alle Styles inline, ein Screen).
- Referenzen im Repo `halle-gehirn`: `docs/taxonomie.md` (Facetten/Vokabular), `data/manifest.yaml` & `data/vokabular.yaml` (echte Werte), `CLAUDE.md` (Stack, SSE, Confidence-Schwellen, Bot-Name „Jarvis“).
