/** HTTP-Client fuer /admin/wissen und /ready Endpoints. */

import type {
  BestandResponse,
  DokumentChunksResponse,
  DokumentCreateResponse,
  DokumentDeleteResponse,
  DokumentMetadata,
  IngestEvent,
  IngestStartResponse,
  MetadataSuggestion,
  ReadyResponse,
  VokabularCreateResponse,
  VokabularResponse,
} from "./types";

const API_KEY = "change-me-in-production";

const headers: Record<string, string> = {
  "X-API-Key": API_KEY,
};

/** Parse error body from non-ok responses. */
async function parseError(resp: Response, fallback: string): Promise<string> {
  try {
    const body = await resp.json();
    if (body.detail) {
      if (typeof body.detail === "string") return body.detail;
      if (Array.isArray(body.detail))
        return body.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    }
    return `${fallback}: ${resp.status}`;
  } catch {
    return `${fallback}: ${resp.status}`;
  }
}

// ── Bestand ──

export async function fetchBestand(): Promise<BestandResponse> {
  const resp = await fetch("/admin/wissen/bestand", { headers });
  if (!resp.ok) throw new Error(await parseError(resp, "Bestand"));
  return resp.json();
}

// ── Infrastruktur ──

export async function checkReady(): Promise<ReadyResponse> {
  try {
    const resp = await fetch("/ready");
    if (!resp.ok) return { status: "error", qdrant: false, ollama: false };
    return resp.json();
  } catch {
    return { status: "error", qdrant: false, ollama: false };
  }
}

export async function checkHealth(): Promise<boolean> {
  try {
    const resp = await fetch("/health");
    return resp.ok;
  } catch {
    return false;
  }
}

// ── Vokabular ──

export async function fetchVokabular(): Promise<VokabularResponse> {
  const resp = await fetch("/admin/wissen/vokabular", { headers });
  if (!resp.ok) throw new Error(await parseError(resp, "Vokabular"));
  return resp.json();
}

export async function createVokabularEntry(
  facet: string,
  slug: string,
  label: string,
): Promise<VokabularCreateResponse> {
  const resp = await fetch("/admin/wissen/vokabular", {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ facet, slug, label }),
  });
  if (!resp.ok) throw new Error(await parseError(resp, "Vokabular anlegen"));
  return resp.json();
}

// ── Dokumente ──

export async function detectMetadata(file: File): Promise<MetadataSuggestion> {
  const form = new FormData();
  form.append("file", file);
  const resp = await fetch("/admin/wissen/dokumente/detect", {
    method: "POST",
    headers: { "X-API-Key": API_KEY },
    body: form,
  });
  if (!resp.ok) throw new Error(await parseError(resp, "Detect"));
  return resp.json();
}

export async function uploadDokument(
  file: File,
  metadata: DokumentMetadata,
): Promise<DokumentCreateResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("metadata", JSON.stringify(metadata));
  const resp = await fetch("/admin/wissen/dokumente", {
    method: "POST",
    headers: { "X-API-Key": API_KEY },
    body: form,
  });
  if (!resp.ok) throw new Error(await parseError(resp, "Upload"));
  return resp.json();
}

export async function fetchDokumentChunks(
  datei: string,
): Promise<DokumentChunksResponse> {
  const resp = await fetch(`/admin/wissen/dokumente/${datei}/chunks`, { headers });
  if (!resp.ok) throw new Error(await parseError(resp, "Chunks"));
  return resp.json();
}

export async function deleteDokument(
  datei: string,
  deleteFile = false,
): Promise<DokumentDeleteResponse> {
  const params = deleteFile ? "?delete_file=true" : "";
  const resp = await fetch(`/admin/wissen/dokumente/${datei}${params}`, {
    method: "DELETE",
    headers,
  });
  if (!resp.ok) throw new Error(await parseError(resp, "Loeschen"));
  return resp.json();
}

// ── Ingest ──

export async function startIngest(
  selectedDateien: string[],
  resetCollection = false,
): Promise<IngestStartResponse> {
  const resp = await fetch("/admin/wissen/ingest", {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({
      selected_dateien: selectedDateien,
      reset_collection: resetCollection,
    }),
  });
  if (!resp.ok) throw new Error(await parseError(resp, "Ingest starten"));
  return resp.json();
}

export function streamIngestProgress(
  jobId: string,
  onEvent: (event: IngestEvent) => void,
  onError: (error: string) => void,
  onDone: () => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`/admin/wissen/ingest/${jobId}/stream`, {
        headers,
        signal: controller.signal,
      });
      if (!resp.ok) {
        onError(await parseError(resp, "Ingest-Stream"));
        return;
      }
      const reader = resp.body?.getReader();
      if (!reader) {
        onError("Kein Stream verfuegbar");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          try {
            const event: IngestEvent = JSON.parse(trimmed.slice(6));
            onEvent(event);
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        onError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      onDone();
    }
  })();

  return () => controller.abort();
}
