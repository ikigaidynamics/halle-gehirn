/** HTTP-Client fuer /admin/wissen und /ready Endpoints. */

import type { BestandResponse, ReadyResponse } from "./types";

const API_KEY = "change-me-in-production";

const headers: Record<string, string> = {
  "X-API-Key": API_KEY,
};

export async function fetchBestand(): Promise<BestandResponse> {
  const resp = await fetch("/admin/wissen/bestand", { headers });
  if (!resp.ok) throw new Error(`Bestand: ${resp.status}`);
  return resp.json();
}

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
