/** TS-Interfaces mirroring backend Pydantic schemas (admin_schemas.py). */

export interface ManifestEntry {
  datei: string;
  titel: string;
  doc_type: string;
  doc_type_label: string;
  bereich: string[];
  bereich_labels: string[];
  herkunft: string;
  herkunft_label: string;
  quelltyp: string;
  vertraulichkeit: string;
  vertraulichkeit_label: string;
  status: string;
  jahr: number | null;
  grad: string | null;
  thema: string[];
  anlage: string[];
  projekt: string[];
  ansprechperson: string[];
  autor: string[];
  file_exists: boolean;
  is_indexed: boolean;
}

export interface IndexedDoc {
  datei: string;
  titel: string;
  chunk_count: number;
  source_hash: string;
  doc_type: string;
  in_manifest: boolean;
}

export interface BestandResponse {
  manifest_entries: ManifestEntry[];
  indexed_docs: IndexedDoc[];
  total_chunks: number;
}

export interface ReadyResponse {
  status: string;
  qdrant: boolean;
  ollama: boolean;
}
