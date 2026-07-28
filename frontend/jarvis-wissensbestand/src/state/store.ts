/** Global state via Preact Signals. */

import { signal } from "@preact/signals";
import { fetchBestand, checkReady } from "../api/admin";
import type { BestandResponse, ReadyResponse } from "../api/types";

// ── Bestand ──
export const bestandData = signal<BestandResponse | null>(null);
export const bestandLoading = signal(false);
export const bestandError = signal<string | null>(null);

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

export async function refreshReady(): Promise<void> {
  readyState.value = await checkReady();
}
