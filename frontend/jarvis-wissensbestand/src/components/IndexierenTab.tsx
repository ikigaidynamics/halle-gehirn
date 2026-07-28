import { useEffect } from "preact/hooks";
import { signal } from "@preact/signals";
import {
  bestandData,
  bestandLoading,
  loadBestand,
  ingestRunning,
  ingestEvents,
  ingestError,
  ingestStats,
  runIngest,
  cancelIngest,
} from "../state/store";
import type { IngestEvent } from "../api/types";

// ── Local state ──
const selectedDateien = signal<Set<string>>(new Set());
const resetCollection = signal(false);
const showOnlyPending = signal(false);

export function IndexierenTab() {
  useEffect(() => {
    if (!bestandData.value) loadBestand();
  }, []);

  if (bestandLoading.value && !bestandData.value) {
    return (
      <div class="flex items-center justify-center py-20 text-text-muted text-[14px]">
        Lade Bestand...
      </div>
    );
  }

  const data = bestandData.value;
  if (!data) return null;

  const entries = showOnlyPending.value
    ? data.manifest_entries.filter((e) => !e.is_indexed && e.file_exists)
    : data.manifest_entries.filter((e) => e.file_exists);

  const selected = selectedDateien.value;
  const allSelected = entries.length > 0 && entries.every((e) => selected.has(e.datei));

  function toggleOne(datei: string) {
    const next = new Set(selected);
    if (next.has(datei)) next.delete(datei);
    else next.add(datei);
    selectedDateien.value = next;
  }

  function selectAll() {
    selectedDateien.value = new Set(entries.map((e) => e.datei));
  }

  function deselectAll() {
    selectedDateien.value = new Set();
  }

  function handleStart() {
    const dateien = [...selectedDateien.value];
    if (dateien.length === 0) return;
    runIngest(dateien, resetCollection.value);
  }

  const lastEvent = ingestEvents.value.length > 0
    ? ingestEvents.value[ingestEvents.value.length - 1]
    : null;
  const isDone = lastEvent?.status === "completed";
  const isFailed = lastEvent?.status === "failed";
  const progress = lastEvent
    ? (lastEvent.doc_total > 0 ? lastEvent.doc_index / lastEvent.doc_total : 0)
    : 0;
  const progressPct = isDone ? 100 : Math.round(progress * 100);

  return (
    <div class="flex gap-6 p-6 h-full overflow-hidden">
      {/* Left: Document Selection */}
      <div class="flex-1 min-w-0 flex flex-col">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-[15px] font-bold text-text-primary">
            Dokumente indexieren
          </h2>
          <div class="flex items-center gap-3">
            <label class="flex items-center gap-[6px] text-[12px] text-text-muted cursor-pointer">
              <input
                type="checkbox"
                checked={showOnlyPending.value}
                onChange={(e) => {
                  showOnlyPending.value = (e.target as HTMLInputElement).checked;
                  deselectAll();
                }}
                class="accent-[#E2001A]"
              />
              Nur nicht-indexierte
            </label>
            <button
              onClick={allSelected ? deselectAll : selectAll}
              disabled={ingestRunning.value}
              class="py-[4px] px-[10px] rounded-md text-[11px] font-medium border cursor-pointer bg-transparent transition-colors"
              style={{
                borderColor: "rgba(0,0,0,0.12)",
                color: "#555",
                opacity: ingestRunning.value ? 0.5 : 1,
              }}
            >
              {allSelected ? "Keine" : "Alle"}
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-auto jv-scroll rounded-lg border border-border bg-surface">
          <table class="w-full text-[13px]">
            <thead>
              <tr class="bg-panel-3 text-text-secondary text-left">
                <th class="py-[10px] px-[14px] font-semibold w-[40px]" />
                <th class="py-[10px] px-[14px] font-semibold">Titel</th>
                <th class="py-[10px] px-[14px] font-semibold w-[120px]">Typ</th>
                <th class="py-[10px] px-[14px] font-semibold w-[90px] text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => {
                const checked = selected.has(entry.datei);
                return (
                  <tr
                    key={entry.datei}
                    class="border-t border-border-light hover:bg-panel-1 transition-colors cursor-pointer"
                    onClick={() => !ingestRunning.value && toggleOne(entry.datei)}
                  >
                    <td class="py-[10px] px-[14px] text-center">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={ingestRunning.value}
                        onChange={() => toggleOne(entry.datei)}
                        onClick={(e) => e.stopPropagation()}
                        class="accent-[#E2001A]"
                      />
                    </td>
                    <td class="py-[10px] px-[14px]">
                      <div class="font-medium text-text-primary truncate">
                        {entry.titel}
                      </div>
                      <div class="text-[11px] text-text-muted font-mono truncate mt-[2px]">
                        {entry.datei}
                      </div>
                    </td>
                    <td class="py-[10px] px-[14px] text-text-secondary">
                      {entry.doc_type_label}
                    </td>
                    <td class="py-[10px] px-[14px] text-center">
                      <span
                        class="inline-flex items-center gap-[5px] py-[3px] px-[8px] rounded-full text-[11px] font-medium"
                        style={{
                          background: entry.is_indexed
                            ? "rgba(47,158,68,0.10)"
                            : "rgba(227,160,8,0.10)",
                          color: entry.is_indexed ? "#2f9e44" : "#e3a008",
                        }}
                      >
                        <span
                          class="w-[5px] h-[5px] rounded-full"
                          style={{
                            background: entry.is_indexed ? "#2f9e44" : "#e3a008",
                          }}
                        />
                        {entry.is_indexed ? "Indexiert" : "Pending"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {entries.length === 0 && (
                <tr>
                  <td colSpan={4} class="py-10 text-center text-text-muted text-[13px]">
                    {showOnlyPending.value
                      ? "Alle Dokumente sind bereits indexiert."
                      : "Keine Dokumente im Manifest."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right: Controls + Progress */}
      <div class="w-[300px] shrink-0 flex flex-col gap-4">
        {/* Start Controls */}
        <div class="p-[18px] rounded-xl bg-surface border border-border">
          <div class="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-3">
            Indexierung
          </div>

          <div class="text-[28px] font-bold text-text-primary leading-none">
            {selected.size}
          </div>
          <div class="text-[12px] text-text-muted mt-1">
            Dokument{selected.size !== 1 ? "e" : ""} ausgewaehlt
          </div>

          <div class="mt-4 pt-3 border-t border-border-light">
            <label class="flex items-center gap-[8px] text-[12px] text-text-secondary cursor-pointer mb-3">
              <input
                type="checkbox"
                checked={resetCollection.value}
                onChange={(e) => {
                  resetCollection.value = (e.target as HTMLInputElement).checked;
                }}
                disabled={ingestRunning.value}
                class="accent-[#f0603a]"
              />
              <span>
                Collection zuruecksetzen
                <span class="block text-[11px] text-text-muted mt-[2px]">
                  Loescht ALLE Chunks vor dem Neuaufbau
                </span>
              </span>
            </label>

            {resetCollection.value && (
              <div
                class="p-[10px] rounded-lg mb-3 text-[11px]"
                style={{
                  background: "rgba(240,96,58,0.06)",
                  border: "1px solid rgba(240,96,58,0.2)",
                  color: "#c0392b",
                }}
              >
                Achtung: Alle bestehenden Chunks werden unwiderruflich geloescht!
              </div>
            )}

            <button
              onClick={handleStart}
              disabled={ingestRunning.value || selected.size === 0}
              class="w-full py-[10px] rounded-lg text-[13px] font-semibold text-white cursor-pointer border-none"
              style={{
                background:
                  ingestRunning.value || selected.size === 0
                    ? "#ccc"
                    : "#E2001A",
              }}
            >
              {ingestRunning.value
                ? "Laeuft..."
                : `Indexierung starten (${selected.size})`}
            </button>
          </div>
        </div>

        {/* Progress Panel */}
        {(ingestRunning.value || lastEvent) && (
          <div class="p-[18px] rounded-xl bg-surface border border-border">
            <div class="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-3">
              Fortschritt
            </div>

            {/* Progress Bar */}
            <div class="w-full h-[6px] bg-panel-4 rounded-full overflow-hidden mb-2">
              <div
                class="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${progressPct}%`,
                  background: isFailed
                    ? "#f0603a"
                    : isDone
                      ? "#2f9e44"
                      : "#E2001A",
                }}
              />
            </div>
            <div class="flex justify-between text-[11px] text-text-muted mb-3">
              <span>{progressPct}%</span>
              {lastEvent?.elapsed_s != null && (
                <span>{formatDuration(lastEvent.elapsed_s)}</span>
              )}
            </div>

            {/* Phase + Detail */}
            {lastEvent && (
              <div class="flex flex-col gap-[6px] text-[12px]">
                <div class="flex items-center gap-2">
                  <span
                    class="py-[2px] px-[6px] rounded text-[10px] font-semibold uppercase tracking-wider"
                    style={{
                      background: phaseColor(lastEvent.phase, 0.1),
                      color: phaseColor(lastEvent.phase, 1),
                    }}
                  >
                    {lastEvent.phase}
                  </span>
                  {lastEvent.datei && (
                    <span class="text-text-muted font-mono truncate text-[11px]">
                      {lastEvent.datei}
                    </span>
                  )}
                </div>
                <div class="text-text-secondary text-[12px]">
                  {lastEvent.detail}
                </div>
                {lastEvent.doc_total > 0 && (
                  <div class="text-text-muted text-[11px]">
                    Dokument {lastEvent.doc_index} / {lastEvent.doc_total}
                  </div>
                )}
              </div>
            )}

            {/* Event Log (scrollable) */}
            <EventLog events={ingestEvents.value} />

            {/* Cancel */}
            {ingestRunning.value && (
              <button
                onClick={cancelIngest}
                class="w-full mt-3 py-[8px] rounded-lg text-[12px] font-medium border cursor-pointer bg-transparent transition-colors"
                style={{
                  borderColor: "rgba(0,0,0,0.12)",
                  color: "#555",
                }}
              >
                Abbrechen
              </button>
            )}
          </div>
        )}

        {/* Error */}
        {ingestError.value && (
          <div
            class="p-[14px] rounded-xl text-[12px]"
            style={{
              background: "rgba(240,96,58,0.08)",
              border: "1px solid rgba(240,96,58,0.28)",
              color: "#c0392b",
            }}
          >
            <div class="font-semibold mb-1">Fehler</div>
            {ingestError.value}
          </div>
        )}

        {/* Stats */}
        {ingestStats.value && !ingestRunning.value && (
          <StatsPanel stats={ingestStats.value} />
        )}
      </div>
    </div>
  );
}

// ── Sub-Components ──

function EventLog({ events }: { events: IngestEvent[] }) {
  if (events.length <= 1) return null;

  return (
    <div class="mt-3 pt-3 border-t border-border-light">
      <div class="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2">
        Log ({events.length})
      </div>
      <div class="max-h-[160px] overflow-auto jv-scroll flex flex-col gap-[3px]">
        {events.map((ev, i) => (
          <div key={i} class="text-[11px] text-text-muted flex gap-2">
            <span
              class="shrink-0 font-mono w-[50px] text-right"
              style={{ color: phaseColor(ev.phase, 1) }}
            >
              {ev.phase}
            </span>
            <span class="truncate">{ev.detail || ev.datei}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatsPanel({ stats }: { stats: import("../api/types").IngestStats }) {
  const hasErrors = stats.errors.length > 0;

  return (
    <div class="p-[18px] rounded-xl bg-surface border border-border">
      <div class="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-3">
        Ergebnis
      </div>
      <div class="flex flex-col gap-[6px]">
        <StatRow label="Dokumente gesamt" value={stats.docs_total} />
        <StatRow label="Erfolgreich" value={stats.docs_success} color="#2f9e44" />
        {stats.docs_unchanged > 0 && (
          <StatRow label="Unveraendert" value={stats.docs_unchanged} color="#e3a008" />
        )}
        {stats.docs_skipped > 0 && (
          <StatRow label="Uebersprungen" value={stats.docs_skipped} color="#e3a008" />
        )}
        {stats.docs_failed > 0 && (
          <StatRow label="Fehlgeschlagen" value={stats.docs_failed} color="#f0603a" />
        )}
        <div class="border-t border-border-light my-1" />
        <StatRow label="Chunks gesamt" value={stats.chunks_total} />
        {stats.chunks_embedded != null && (
          <StatRow label="Embedded" value={stats.chunks_embedded} />
        )}
        {stats.chunks_upserted != null && (
          <StatRow label="In Qdrant" value={stats.chunks_upserted} color="#2f9e44" />
        )}
        {(stats.chunks_stale_deleted ?? 0) > 0 && (
          <StatRow
            label="Stale geloescht"
            value={stats.chunks_stale_deleted!}
            color="#f0603a"
          />
        )}
      </div>

      {hasErrors && (
        <div class="mt-3 pt-3 border-t border-border-light">
          <div class="text-[11px] font-semibold text-[#c0392b] mb-1">
            Fehler ({stats.errors.length})
          </div>
          <div class="max-h-[100px] overflow-auto jv-scroll">
            {stats.errors.map((err, i) => (
              <div key={i} class="text-[11px] text-[#c0392b] mb-1">
                {err}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatRow({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div class="flex justify-between text-[12px]">
      <span class="text-text-muted">{label}</span>
      <span
        class="font-mono font-medium"
        style={{ color: color ?? "var(--color-text-secondary)" }}
      >
        {value}
      </span>
    </div>
  );
}

// ── Helpers ──

function phaseColor(phase: string, alpha: number): string {
  const colors: Record<string, string> = {
    reset: `rgba(240,96,58,${alpha})`,
    extract: `rgba(59,130,246,${alpha})`,
    chunk: `rgba(139,92,246,${alpha})`,
    enrich: `rgba(227,160,8,${alpha})`,
    embed: `rgba(16,185,129,${alpha})`,
    upsert: `rgba(47,158,68,${alpha})`,
    done: `rgba(47,158,68,${alpha})`,
    error: `rgba(240,96,58,${alpha})`,
  };
  return colors[phase] ?? `rgba(138,135,127,${alpha})`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}
