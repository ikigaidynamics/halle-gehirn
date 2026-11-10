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

// ── Vokabular ──

export interface VokabularResponse {
  choices: Record<string, Record<string, string>>;
  sorten: string[];
}

// ── Metadata Detection ──

export interface MetadataSuggestion {
  titel: string;
  doc_type: string | null;
  grad: string | null;
  bereich: string[];
  herkunft: string;
  quelltyp: string;
  vertraulichkeit: string;
  status: string;
  jahr: number | null;
  sorte: string | null;
  autor_vorschlag: string | null;
  ansprechperson_vorschlag: string[];
  studiengang: string | null;
}

// ── Dokument CRUD ──

export interface DokumentMetadata {
  sorte: string;
  titel: string;
  doc_type: string;
  bereich: string[];
  herkunft: string;
  quelltyp: string;
  vertraulichkeit: string;
  status: string;
  jahr: number | null;
  grad: string | null;
  thema: string[];
  anlage: string[];
  projekt: string[];
  ansprechperson: string[];
  autor: string[];
}

export interface DokumentCreateResponse {
  status: string;
  datei: string;
  titel: string;
}

export interface DokumentDeleteResponse {
  status: string;
  datei: string;
  deleted_from_manifest: boolean;
  deleted_from_qdrant: boolean;
  deleted_chunks: number;
  deleted_file: boolean;
}

export interface VokabularCreateResponse {
  status: string;
  facet: string;
  slug: string;
  label: string;
}

// ── Chunk-Inspektion ──

export interface ChunkDetail {
  chunk_index: number;
  breadcrumb: string | null;
  context_prefix: string | null;
  text: string;
  page: number | null;
  is_table: boolean;
  token_count: number;
  source_hash: string;
  disabled: boolean;
  figure_refs: string[];
  figure_captions: string[];
}

export interface DokumentChunksResponse {
  datei: string;
  titel: string;
  chunk_count: number;
  chunks: ChunkDetail[];
}

// ── Ingest ──

export interface IngestStartResponse {
  status: string;
  job_id: string;
  message: string;
}

export interface IngestJobStatus {
  job_id: string;
  status: string;
  progress: number;
  phase: string;
  current_datei: string;
  detail: string;
  stats: IngestStats | null;
  error: string | null;
}

export interface IngestStats {
  docs_total: number;
  docs_success: number;
  docs_skipped: number;
  docs_unchanged: number;
  docs_failed: number;
  chunks_total: number;
  errors: string[];
  chunks_embedded?: number;
  chunks_upserted?: number;
  chunks_stale_deleted?: number;
}

export interface IngestEvent {
  phase: string;
  datei: string;
  doc_index: number;
  doc_total: number;
  detail: string;
  chunks_so_far?: number;
  chunks_total?: number;
  elapsed_s?: number;
  status?: string;
  stats?: IngestStats;
}
