/** Global state via Preact Signals. */

import { signal } from "@preact/signals";
import {
  fetchBestand,
  fetchVokabular,
  checkReady,
  deleteDokument,
  startIngest,
  streamIngestProgress,
} from "../api/admin";
import type {
  BestandResponse,
  DokumentDeleteResponse,
  IngestEvent,
  IngestStats,
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

// ── Ingest ──

export const ingestRunning = signal(false);
export const ingestJobId = signal<string | null>(null);
export const ingestEvents = signal<IngestEvent[]>([]);
export const ingestError = signal<string | null>(null);
export const ingestStats = signal<IngestStats | null>(null);

let _cancelStream: (() => void) | null = null;

export async function runIngest(
  selectedDateien: string[],
  resetCollection: boolean,
): Promise<void> {
  ingestRunning.value = true;
  ingestError.value = null;
  ingestEvents.value = [];
  ingestStats.value = null;

  try {
    const resp = await startIngest(selectedDateien, resetCollection);
    ingestJobId.value = resp.job_id;

    _cancelStream = streamIngestProgress(
      resp.job_id,
      (event: IngestEvent) => {
        ingestEvents.value = [...ingestEvents.value, event];
        if (event.stats) {
          ingestStats.value = event.stats;
        }
      },
      (error: string) => {
        ingestError.value = error;
      },
      () => {
        ingestRunning.value = false;
        _cancelStream = null;
        // Refresh bestand after ingest completes
        loadBestand();
      },
    );
  } catch (err) {
    ingestError.value = err instanceof Error ? err.message : String(err);
    ingestRunning.value = false;
  }
}

export function cancelIngest(): void {
  if (_cancelStream) {
    _cancelStream();
    _cancelStream = null;
  }
  ingestRunning.value = false;
}
