/** Global state via Preact Signals. */

import { signal } from "@preact/signals";
import {
  fetchBestand,
  fetchVokabular,
  checkReady,
  deleteDokument,
} from "../api/admin";
import type {
  BestandResponse,
  DokumentDeleteResponse,
  ReadyResponse,
  VokabularResponse,
} from "../api/types";

// ── Bestand ──
export const bestandData = signal<BestandResponse | null>(null);
export const bestandLoading = signal(false);
export const bestandError = signal<string | null>(null);

// ── Vokabular ──
export const vokabular = signal<VokabularResponse | null>(null);

// ── Infrastruktur ──
export const readyState = signal<ReadyResponse | null>(null);

// ── Navigation ──
export const activeTab = signal<"bestand" | "neu" | "indexieren">("bestand");

// ── Actions ──

export async function loadBestand(): Promise<void> {
  bestandLoading.value = true;
  bestandError.value = null;
  try {
    bestandData.value = await fetchBestand();
  } catch (err) {
    bestandError.value = err instanceof Error ? err.message : String(err);
  } finally {
    bestandLoading.value = false;
  }
}

export async function loadVokabular(): Promise<void> {
  try {
    vokabular.value = await fetchVokabular();
  } catch {
    // Silently retry on next access
  }
}

export async function refreshReady(): Promise<void> {
  readyState.value = await checkReady();
}

export async function removeDokument(
  datei: string,
  deleteFile: boolean,
): Promise<DokumentDeleteResponse> {
  const result = await deleteDokument(datei, deleteFile);
  // Refresh bestand after delete
  await loadBestand();
  return result;
}
