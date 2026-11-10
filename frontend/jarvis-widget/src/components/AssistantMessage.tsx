import type { JSX } from "preact";
import { useState, useEffect } from "preact/hooks";
import type { Source, LatencyStats } from "../api/chat";
import { confidenceFromString } from "../lib/confidence";
import { markdownToHtml } from "../lib/markdown";
import { selectSource, selectedSourceId, selectedMsgIdx } from "../state/store";

interface Props {
  content: string;
  sources: Source[];
  confidence: string;
  groundingScore?: number;
  isStreaming?: boolean;
  msgIdx: number;
  latencyMs?: number;
  stats?: LatencyStats;
  streamStartTime?: number;
}

/** Format milliseconds as human-readable string */
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** Strip the LLM-generated "Quellen:" footer before citation parsing.
 *  Must run BEFORE [S1] splitting because the footer contains [S1] markers. */
const QUELLEN_FOOTER_RE =
  /\n*\s*Quellen:\s*\[S\d+\][\s\S]*$/;

/** Parse [S1], [S2] etc. in answer text and replace with citation buttons.
 *  Text segments are rendered as parsed markdown HTML. */
function renderContentWithCitations(
  rawText: string,
  sources: Source[],
  msgIdx: number,
): JSX.Element[] {
  // Strip "Quellen:" footer first (before [S1] splitting)
  const text = rawText.replace(QUELLEN_FOOTER_RE, "").trimEnd();

  const parts: JSX.Element[] = [];
  const regex = /\[S(\d+)\]/g;
  let lastIdx = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    // Text before the marker — render as markdown HTML
    if (match.index > lastIdx) {
      const segment = text.slice(lastIdx, match.index);
      parts.push(
        <span dangerouslySetInnerHTML={{ __html: markdownToHtml(segment) }} />,
      );
    }

    const num = parseInt(match[1], 10);
    const sourceId = `S${num}`;
    const isActive = selectedSourceId.value === sourceId && selectedMsgIdx.value === msgIdx;
    const exists = sources.some((s) => s.id === sourceId);

    if (exists) {
      parts.push(
        <button
          onClick={() => selectSource(sourceId, msgIdx)}
          class="inline-flex items-center justify-center w-[18px] h-[18px] p-0 mx-[2px] rounded-full font-mono text-[10px] font-semibold leading-none border-none cursor-pointer align-top"
          style={{
            background: isActive ? "#E2001A" : "rgba(226,0,26,0.14)",
            color: isActive ? "#fff" : "#E2001A",
          }}
        >
          {num}
        </button>,
      );
    } else {
      parts.push(<span>{match[0]}</span>);
    }

    lastIdx = match.index + match[0].length;
  }

  if (lastIdx < text.length) {
    const segment = text.slice(lastIdx);
    parts.push(
      <span dangerouslySetInnerHTML={{ __html: markdownToHtml(segment) }} />,
    );
  }

  return parts;
}

/** Aufklappbare Statistik-Komponente */
function StatsCollapsible({ stats, latencyMs }: { stats: LatencyStats; latencyMs?: number }) {
  const [open, setOpen] = useState(false);

  // Berechne Prozentanteile für visuelle Darstellung
  const total = stats.total_ms || 1;
  const stages = [
    { name: "Query-Rewrite", ms: stats.rewrite_ms, color: "#8b5cf6" },
    { name: "Embedding", ms: stats.embed_ms, color: "#3b82f6" },
    { name: "Qdrant-Suche", ms: stats.search_ms, color: "#10b981" },
    { name: "Reranking", ms: stats.rerank_ms, color: stats.rerank_ms > 1000 ? "#dc2626" : "#f59e0b" },
    { name: "LLM-Generierung", ms: stats.generate_ms, color: "#6366f1" },
  ].filter(s => s.ms > 0);

  return (
    <div class="mt-3 pt-[11px] border-t border-border-light">
      <button
        onClick={() => setOpen(!open)}
        class="flex items-center gap-[6px] w-full text-left bg-transparent border-none cursor-pointer p-0"
        style={{ color: "#888" }}
      >
        <span
          class="text-[10px] transition-transform"
          style={{ transform: open ? "rotate(90deg)" : "rotate(0deg)" }}
        >
          ▶
        </span>
        <span class="font-mono text-[10px] font-medium">
          ⏱ {formatDuration(latencyMs || stats.total_ms)}
        </span>
        <span class="text-[10px]" style={{ opacity: 0.6 }}>
          — Statistik {open ? "ausblenden" : "anzeigen"}
        </span>
      </button>

      {open && (
        <div class="mt-2">
          {/* Progress Bar Visualisierung */}
          <div
            class="flex h-[6px] rounded-full overflow-hidden mb-3"
            style={{ background: "rgba(0,0,0,0.06)" }}
          >
            {stages.map((stage) => (
              <div
                key={stage.name}
                style={{
                  width: `${(stage.ms / total) * 100}%`,
                  background: stage.color,
                  minWidth: stage.ms > 0 ? "2px" : "0",
                }}
                title={`${stage.name}: ${formatDuration(stage.ms)}`}
              />
            ))}
          </div>

          {/* Detaillierte Tabelle */}
          <div
            class="grid gap-[4px] text-[10px] font-mono p-2 rounded"
            style={{ background: "rgba(0,0,0,0.02)", gridTemplateColumns: "auto 1fr auto auto" }}
          >
            {stages.map((stage) => {
              const pct = ((stage.ms / total) * 100).toFixed(1);
              return (
                <>
                  <span
                    class="w-[8px] h-[8px] rounded-sm"
                    style={{ background: stage.color }}
                  />
                  <span style={{ color: stage.color === "#dc2626" ? "#dc2626" : "#555" }}>
                    {stage.name}
                  </span>
                  <span style={{ color: "#999", textAlign: "right" }}>{pct}%</span>
                  <span style={{
                    color: stage.color === "#dc2626" ? "#dc2626" : "#333",
                    fontWeight: 600,
                    textAlign: "right",
                    minWidth: "55px"
                  }}>
                    {formatDuration(stage.ms)}
                  </span>
                </>
              );
            })}

            {/* Trennlinie */}
            <div style={{ gridColumn: "1 / -1", borderTop: "1px solid rgba(0,0,0,0.08)", margin: "4px 0" }} />

            {/* Gesamt */}
            <span />
            <span style={{ color: "#333", fontWeight: 600 }}>Pipeline gesamt</span>
            <span style={{ color: "#999", textAlign: "right" }}>100%</span>
            <span style={{ color: "#333", fontWeight: 700, textAlign: "right" }}>
              {formatDuration(stats.total_ms)}
            </span>

            {latencyMs && latencyMs !== stats.total_ms && (
              <>
                <span />
                <span style={{ color: "#888" }}>End-to-End</span>
                <span />
                <span style={{ color: "#666", fontWeight: 600, textAlign: "right" }}>
                  {formatDuration(latencyMs)}
                </span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Build source labels — repeated titles show section/page instead of "ebenda". */
function buildSourceLabels(sources: Source[]): { id: string; label: string }[] {
  const seen = new Map<string, number>(); // title → first occurrence index
  return sources.map((s) => {
    const num = s.id.replace("S", "");
    const title = s.titel || s.datei || `Quelle ${num}`;
    const prevIdx = seen.get(title);
    if (prevIdx !== undefined) {
      // Same title seen before — show abbreviated title + section/page
      const section = s.breadcrumb || (s.page != null ? `S. ${s.page}` : "");
      const short = title.length > 35 ? title.slice(0, 32) + "\u2026" : title;
      return { id: s.id, label: `${num} ${short}${section ? `, ${section}` : ""}` };
    }
    seen.set(title, parseInt(num, 10));
    return { id: s.id, label: `${num} ${title}` };
  });
}

export function AssistantMessage({
  content,
  sources,
  confidence,
  groundingScore,
  isStreaming,
  msgIdx,
  latencyMs,
  stats,
  streamStartTime,
}: Props) {
  const conf = confidence ? confidenceFromString(confidence) : null;
  const sourceLabels = !isStreaming && sources.length > 0
    ? buildSourceLabels(sources)
    : [];

  // Live timer during streaming
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!isStreaming || !streamStartTime) {
      setElapsed(0);
      return;
    }
    const interval = setInterval(() => {
      setElapsed(Date.now() - streamStartTime);
    }, 100);
    return () => clearInterval(interval);
  }, [isStreaming, streamStartTime]);

  return (
    <div class="flex gap-3">
      {/* KI Fabrik Scout Avatar */}
      <img
        src="/MDZ_Icon.jpg"
        alt="KI Fabrik Scout"
        class="w-[30px] h-[30px] rounded-[9px] shrink-0 object-cover"
        style={{ boxShadow: "0 0 0 1px rgba(226,0,26,0.25)" }}
      />

      <div class="min-w-0">
        {/* Live Timer während Streaming */}
        {isStreaming && streamStartTime && (
          <div
            class="flex items-center gap-[6px] py-[4px] px-[10px] rounded-lg w-fit mb-[9px] font-mono text-[11px]"
            style={{
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.2)",
              color: "#3b82f6",
            }}
          >
            <span class="inline-block w-[6px] h-[6px] rounded-full bg-blue-500 animate-pulse"
                  style={{ background: "#3b82f6" }} />
            <span style={{ fontWeight: 600 }}>{formatDuration(elapsed)}</span>
            <span style={{ opacity: 0.7 }}>Generiere...</span>
          </div>
        )}

        {/* Confidence Ampel + Latenz Badge (shown after streaming) */}
        {!isStreaming && (
          <div class="flex items-center gap-[8px] mb-[9px] flex-wrap">
            {/* Confidence Ampel */}
            {conf && (
              <div
                class="flex items-center gap-[7px] py-[5px] px-[11px] rounded-lg"
                style={{
                  background: conf.bgColor,
                  border: `1px solid ${conf.borderColor}`,
                }}
              >
                <span class="flex gap-[3px]">
                  <span
                    class="w-[7px] h-[7px] rounded-full"
                    style={{
                      background:
                        conf.level === "gruen"
                          ? "#2f9e44"
                          : "rgba(47,158,68,0.28)",
                      boxShadow:
                        conf.level === "gruen"
                          ? "0 0 6px rgba(47,158,68,0.5)"
                          : "none",
                    }}
                  />
                  <span
                    class="w-[7px] h-[7px] rounded-full"
                    style={{
                      background:
                        conf.level === "gelb"
                          ? "#e3a008"
                          : "rgba(227,160,8,0.28)",
                      boxShadow:
                        conf.level === "gelb"
                          ? "0 0 6px rgba(227,160,8,0.5)"
                          : "none",
                    }}
                  />
                  <span
                    class="w-[7px] h-[7px] rounded-full"
                    style={{
                      background:
                        conf.level === "rot"
                          ? "#f0603a"
                          : "rgba(240,96,58,0.28)",
                      boxShadow:
                        conf.level === "rot"
                          ? "0 0 6px rgba(240,96,58,0.5)"
                          : "none",
                    }}
                  />
                </span>
                <span
                  class="text-[11.5px] font-semibold"
                  style={{ color: conf.color }}
                >
                  {conf.label}
                  {groundingScore != null && groundingScore > 0 && ` · Grounding ${groundingScore.toFixed(2)}`}
                </span>
              </div>
            )}

            {/* Latenz Badge */}
            {latencyMs && (
              <div
                class="flex items-center gap-[5px] py-[5px] px-[10px] rounded-lg font-mono text-[11px]"
                style={{
                  background: latencyMs > 10000 ? "rgba(220, 38, 38, 0.08)" : "rgba(0, 0, 0, 0.04)",
                  border: latencyMs > 10000 ? "1px solid rgba(220, 38, 38, 0.2)" : "1px solid rgba(0, 0, 0, 0.08)",
                  color: latencyMs > 10000 ? "#dc2626" : "#666",
                }}
              >
                <span style={{ fontSize: "10px" }}>⏱</span>
                <span style={{ fontWeight: 600 }}>{formatDuration(latencyMs)}</span>
              </div>
            )}

            {/* Token-Länge */}
            {content && (
              <div
                class="flex items-center gap-[5px] py-[5px] px-[10px] rounded-lg font-mono text-[11px]"
                style={{
                  background: "rgba(0, 0, 0, 0.04)",
                  border: "1px solid rgba(0, 0, 0, 0.08)",
                  color: "#666",
                }}
              >
                <span style={{ fontSize: "10px" }}>📝</span>
                <span style={{ fontWeight: 600 }}>{content.length}</span>
                <span style={{ opacity: 0.7 }}>Zeichen</span>
              </div>
            )}
          </div>
        )}

        {/* Message Bubble */}
        <div
          class="py-[15px] px-[17px] bg-surface text-[14px] leading-[1.72] text-text-body"
          style={{
            borderRadius: "14px",
            borderTopLeftRadius: "5px",
            border: "1px solid rgba(0,0,0,0.08)",
            boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
          }}
        >
          {/* Content with inline citation markers */}
          <div>
            {isStreaming ? (
              <>
                <span
                  dangerouslySetInnerHTML={{
                    __html: markdownToHtml(content),
                  }}
                />
                <span class="caret-blink" />
              </>
            ) : (
              renderContentWithCitations(content, sources, msgIdx)
            )}
          </div>

          {/* Source pills footer — with titles + ebenda */}
          {sourceLabels.length > 0 && (
            <div class="mt-3 pt-[11px] border-t border-border-light">
              <div class="font-mono text-[10px] font-medium text-text-faint mb-[6px]">
                {sources.length} {sources.length === 1 ? "Beleg" : "Belege"}
              </div>
              <div class="flex flex-col gap-[4px]">
                {sourceLabels.map(({ id, label }) => {
                  const isActive = selectedSourceId.value === id && selectedMsgIdx.value === msgIdx;
                  const num = id.replace("S", "");
                  return (
                    <button
                      key={id}
                      onClick={() => selectSource(id, msgIdx)}
                      class="flex items-center gap-[8px] px-[10px] py-[5px] rounded-lg text-left border-none cursor-pointer w-full"
                      style={{
                        background: isActive
                          ? "rgba(226,0,26,0.10)"
                          : "rgba(0,0,0,0.02)",
                        border: isActive
                          ? "1px solid rgba(226,0,26,0.25)"
                          : "1px solid transparent",
                      }}
                    >
                      <span
                        class="inline-flex items-center justify-center w-[18px] h-[18px] rounded-full font-mono text-[10px] font-semibold leading-none shrink-0"
                        style={{
                          background: isActive
                            ? "#E2001A"
                            : "rgba(226,0,26,0.14)",
                          color: isActive ? "#fff" : "#E2001A",
                        }}
                      >
                        {num}
                      </span>
                      <span
                        class="text-[11.5px] truncate"
                        style={{ color: "#555" }}
                      >
                        {label.slice(num.length + 1)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Latency Stats - Aufklappbar */}
          {stats && !isStreaming && (
            <StatsCollapsible stats={stats} latencyMs={latencyMs} />
          )}
        </div>
      </div>
    </div>
  );
}
