/** Slug-to-display mapping for metadata facets (from vokabular.yaml). */

/** Field slug -> German display label. */
export const FIELD_LABELS: Record<string, string> = {
  doc_type: "Dokumententyp",
  grad: "Grad",
  bereich: "Bereich",
  anlage: "Anlage",
  thema: "Thema",
  ansprechperson: "Ansprechperson",
  jahr: "Jahr",
  herkunft: "Herkunft",
  quelltyp: "Quelltyp",
  vertraulichkeit: "Vertraulichkeit",
  status: "Status",
  autor: "Autor",
  projekt: "Projekt",
  page: "Seite",
};

/** Value slug -> display text, per facet. */
export const VALUE_LABELS: Record<string, Record<string, string>> = {
  doc_type: {
    abschlussarbeit: "Abschlussarbeit",
    projektbericht: "Projektbericht",
    handbuch: "Handbuch",
    anlagendoku: "Anlagendokumentation",
    transkript: "Transkript",
    transfer: "Transfer-Dokument",
    fachartikel: "Fachartikel",
    vortrag: "Vortrag/Praesentation",
  },
  grad: {
    bachelor: "Bachelor",
    master: "Master",
    diplom: "Diplom",
    promotion: "Promotion",
  },
  bereich: {
    forschung: "Forschung",
    infrastruktur: "Infrastruktur",
    transfer: "Transfer",
    lehre: "Lehre",
  },
  herkunft: {
    lehrstuhl_at: "Lehrstuhl Automatisierungstechnik",
    mdz_spreeland: "MDZ Spreeland",
    extern: "Extern",
  },
  quelltyp: {
    primaer: "Primaerquelle",
    kuratiert: "Kuratiert",
    synthetisch: "Synthetisch",
  },
  vertraulichkeit: {
    offen: "Offen",
    intern: "Intern",
    vertraulich: "Vertraulich",
  },
  status: {
    final: "Final",
    entwurf: "Entwurf",
    archiviert: "Archiviert",
  },
  thema: {
    mensch_roboter_kollaboration: "Mensch-Roboter-Kollaboration",
    mensch_maschine_interaktion: "Simulationsgestuetzte Mensch-Maschine-Interaktion",
    vernetzte_steuerungstechnik: "Vernetzte Steuerungstechnik",
  },
  anlage: {
    vier_gewinnt: "Roboterloesung 'Vier gewinnt'",
    ftf_agv: "Fahrerloses Transportsystem / AGV",
    gestenerkennung: "Assistenzsystem mit Gestenerkennung",
    kuka_industrieroboter: "KUKA-Industrieroboter",
    leichtbauroboter: "Leichtbauroboter / Cobot",
    kooperierende_roboter: "Kooperierende Roboter",
    werkzeugmaschine: "Werkzeugmaschine",
    greifroboter: "Greifroboter",
    predictive_maintenance: "Predictive-Maintenance-Pruefstand",
    ur10e: "Universal Robots UR10e",
    datenhandschuhe: "Datenhandschuhe",
  },
  ansprechperson: {
    berger: "Prof. Berger",
    bork: "Christian Bork",
    jost: "Robin Jost",
    lautsch: "Martin Lautsch",
  },
  projekt: {
    direct: "DIRECT",
    lufo: "LuFo",
  },
};

/** Resolve a value slug to its display text. Falls back to the slug itself. */
export function displayValue(facet: string, slug: string): string {
  return VALUE_LABELS[facet]?.[slug] ?? slug;
}

/** Resolve a list of value slugs. */
export function displayValues(facet: string, slugs: string[]): string {
  return slugs.map((s) => displayValue(facet, s)).join(", ");
}
