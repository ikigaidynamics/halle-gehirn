/** HTTP-Client fuer /admin/wissen und /ready Endpoints. */

import type {
  BestandResponse,
  DokumentChunksResponse,
  DokumentCreateResponse,
  DokumentDeleteResponse,
  DokumentMetadata,
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
