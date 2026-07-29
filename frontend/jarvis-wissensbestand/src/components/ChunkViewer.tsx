import { signal } from "@preact/signals";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchDokumentChunks, toggleChunkDisabled } from "../api/admin";
import type { DokumentChunksResponse } from "../api/types";

// ── State ──
const chunksData = signal<DokumentChunksResponse | null>(null);
const chunksLoading = signal(false);
const chunksError = signal<string | null>(null);
const selectedDatei = signal<string | null>(null);
const togglingChunk = signal<number | null>(null);

export function openChunkViewer(datei: string) {
  selectedDatei.value = datei;
  chunksData.value = null;
  chunksError.value = null;
  chunksLoading.value = true;
  fetchDokumentChunks(datei)
    .then((data) => { chunksData.value = data; })
    .catch((err) => { chunksError.value = err instanceof Error ? err.message : String(err); })
    .finally(() => { chunksLoading.value = false; });
}

export function closeChunkViewer() {
  selectedDatei.value = null;
  chunksData.value = null;
}

function handleToggle(datei: string, chunkIndex: number, currentDisabled: boolean) {
  togglingChunk.value = chunkIndex;
  toggleChunkDisabled(datei, chunkIndex, !currentDisabled)
    .then(() => {
      // Reload chunks to get fresh state
      fetchDokumentChunks(datei)
        .then((data) => { chunksData.value = data; })
        .catch(() => {});
    })
    .catch((err) => {
      chunksError.value = err instanceof Error ? err.message : String(err);
    })
    .finally(() => { togglingChunk.value = null; });
}

export function ChunkViewer() {
  if (!selectedDatei.value) return null;

  const data = chunksData.value;
  const tables = data?.chunks.filter((c) => c.is_table).length ?? 0;
  const totalTokens = data?.chunks.reduce((s, c) => s + c.token_count, 0) ?? 0;
  const disabledCount = data?.chunks.filter((c) => c.disabled).length ?? 0;

  return (
    <div
      class="fixed inset-0 z-50 flex"
      style={{ background: "rgba(0,0,0,0.4)" }}
      onClick={(e) => { if (e.target === e.currentTarget) closeChunkViewer(); }}
    >
      <div class="m-auto bg-surface rounded-xl shadow-xl flex flex-col"
        style={{ width: "min(90vw, 900px)", height: "min(90vh, 800px)" }}>

        {/* Header */}
        <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div class="min-w-0">
            <h3 class="text-[15px] font-bold text-text-primary truncate">
              {data?.titel ?? selectedDatei.value}
            </h3>
            <div class="text-[11px] text-text-muted font-mono truncate mt-[2px]">
              {selectedDatei.value}
            </div>
          </div>
          <button
            onClick={closeChunkViewer}
            class="shrink-0 ml-4 w-[28px] h-[28px] flex items-center justify-center rounded-md text-[16px] text-text-muted cursor-pointer bg-transparent border border-border-light hover:bg-panel-2 transition-colors"
          >
            &times;
          </button>
        </div>

        {/* Stats bar */}
        {data && (
          <div class="flex items-center gap-4 px-5 py-[10px] bg-panel-1 border-b border-border-light text-[11px] text-text-muted shrink-0">
            <span><strong class="text-text-secondary">{data.chunk_count}</strong> Chunks</span>
            <span><strong class="text-text-secondary">{totalTokens.toLocaleString("de-DE")}</strong> Tokens (approx.)</span>
            {tables > 0 && <span><strong class="text-text-secondary">{tables}</strong> Tabellen</span>}
            {disabledCount > 0 && (
              <span style={{ color: "#f0603a" }}>
                <strong>{disabledCount}</strong> deaktiviert
              </span>
            )}
          </div>
        )}

        {/* Content */}
        <div class="flex-1 overflow-auto jv-scroll px-5 py-4">
          {chunksLoading.value && (
            <div class="flex items-center justify-center py-16 text-text-muted text-[13px]">
              Lade Chunks...
            </div>
          )}

          {chunksError.value && (
            <div class="p-4 rounded-lg text-[13px]"
              style={{ background: "rgba(240,96,58,0.08)", border: "1px solid rgba(240,96,58,0.28)", color: "#c0392b" }}>
              {chunksError.value}
            </div>
          )}

          {data && data.chunks.map((chunk) => (
            <div key={chunk.chunk_index}
              class="mb-4 rounded-lg border overflow-hidden transition-opacity"
              style={{
                borderColor: chunk.disabled
                  ? "rgba(240,96,58,0.25)"
                  : "var(--color-border-light, rgba(0,0,0,0.08))",
                opacity: chunk.disabled ? 0.45 : 1,
              }}>

              {/* Chunk header */}
              <div class="flex items-center gap-3 px-4 py-[8px] bg-panel-2 text-[11px]">
                <span class="font-mono font-bold text-text-secondary">
                  #{chunk.chunk_index}
                </span>
                {chunk.breadcrumb && (
                  <span class="text-text-muted truncate" title={chunk.breadcrumb}>
                    {chunk.breadcrumb}
                  </span>
                )}
                <span class="ml-auto flex items-center gap-3 shrink-0">
                  {chunk.disabled && (
                    <span class="py-[1px] px-[6px] rounded text-[10px] font-semibold"
                      style={{ background: "rgba(240,96,58,0.10)", color: "#f0603a" }}>
                      Deaktiviert
                    </span>
                  )}
                  {chunk.page != null && (
                    <span class="text-text-muted">S. {chunk.page}</span>
                  )}
                  <span class="font-mono text-text-muted">
                    {chunk.token_count} tok
                  </span>
                  {chunk.is_table && (
                    <span class="py-[1px] px-[6px] rounded text-[10px] font-semibold"
                      style={{ background: "rgba(226,0,26,0.08)", color: "#E2001A" }}>
                      Tabelle
                    </span>
                  )}
                  {/* Toggle button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggle(selectedDatei.value!, chunk.chunk_index, chunk.disabled);
                    }}
                    disabled={togglingChunk.value === chunk.chunk_index}
                    class="py-[2px] px-[8px] rounded text-[10px] font-medium cursor-pointer border transition-colors"
                    title={chunk.disabled
                      ? "Im Chatbot wieder beruecksichtigen"
                      : "Aus Chatbot-Suche ausschliessen"}
                    style={{
                      background: chunk.disabled
                        ? "rgba(47,158,68,0.08)"
                        : "rgba(240,96,58,0.06)",
                      borderColor: chunk.disabled
                        ? "rgba(47,158,68,0.25)"
                        : "rgba(240,96,58,0.2)",
                      color: chunk.disabled ? "#2f9e44" : "#c0392b",
                      opacity: togglingChunk.value === chunk.chunk_index ? 0.5 : 1,
                    }}
                  >
                    {togglingChunk.value === chunk.chunk_index
                      ? "..."
                      : chunk.disabled
                        ? "Aktivieren"
                        : "Deaktivieren"}
                  </button>
                </span>
              </div>

              {/* Context prefix (LLM-generated — visually distinct) */}
              {chunk.context_prefix && (
                <div class="px-4 py-[8px] text-[11.5px] leading-[1.6] italic"
                  style={{
                    background: "rgba(227,160,8,0.06)",
                    borderBottom: "1px solid rgba(227,160,8,0.15)",
                    color: "#8a6d00",
                  }}>
                  <span class="not-italic font-semibold text-[10px] uppercase tracking-wider mr-2"
                    style={{ color: "#b8960a" }}>
                    Context-Prefix
                  </span>
                  {chunk.context_prefix}
                </div>
              )}

              {/* Chunk text (markdown rendered) */}
              <div class="px-4 py-3 text-[12.5px] leading-[1.7] text-text-body jv-chunk-md">
                <Markdown remarkPlugins={[remarkGfm]}>{chunk.text}</Markdown>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
