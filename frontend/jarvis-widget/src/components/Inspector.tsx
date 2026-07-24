import { useState } from "preact/hooks";
import { FileText, ExternalLink, ChevronDown, ChevronUp } from "lucide-preact";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { selectedSource, selectedMessage, selectedSourceId } from "../state/store";
import { FIELD_LABELS, displayValue, displayValues } from "../lib/vocab";
import { confidenceFromString } from "../lib/confidence";
import { stripInlineCitations } from "../lib/sanitize";

/** Metadata fields to display, in order. */
const META_FIELDS = [
  "doc_type",
  "bereich",
  "herkunft",
  "quelltyp",
  "vertraulichkeit",
  "status",
  "jahr",
  "grad",
  "thema",
  "anlage",
  "projekt",
  "ansprechperson",
  "autor",
] as const;

/** Fields whose values are shown in primary red. */
const RED_FIELDS = new Set(["bereich", "anlage"]);

/** Max chars before collapsing the chunk. */
const CHUNK_COLLAPSE_CHARS = 300;

function MetadataRow({ field, value }: { field: string; value: string }) {
  const isQuelltyp = field === "quelltyp" && value === "primaer";

  return (
    <>
      <div class="py-2 px-[13px] text-[11.5px] font-medium text-text-muted border-t border-border-light">
        {FIELD_LABELS[field] ?? field}
      </div>
      <div class="py-2 px-[13px] text-[11.5px] font-semibold border-t border-border-light">
        {isQuelltyp ? (
          <span
            class="py-[2px] px-2 rounded-[5px] text-[10.5px] font-semibold"
            style={{
              background: "rgba(47,158,68,0.12)",
              color: "#2f9e44",
            }}
          >
            {displayValue(field, value)}
          </span>
        ) : (
          <span style={{ color: RED_FIELDS.has(field) ? "#E2001A" : "#2a2a2a" }}>
            {displayValue(field, value)}
          </span>
        )}
      </div>
    </>
  );
}

function AntiHallucinationCard({
  label,
  value,
  valueColor,
  passed = true,
}: {
  label: string;
  value: string;
  valueColor: string;
  passed?: boolean;
}) {
  return (
    <div class="flex items-center gap-[10px] py-[10px] px-3 rounded-[10px] bg-panel-1 border border-border/70">
      <span
        class="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[10px]"
        style={{
          background: passed ? "rgba(47,158,68,0.15)" : "rgba(240,96,58,0.15)",
          color: passed ? "#2f9e44" : "#f0603a",
        }}
      >
        {passed ? "\u2713" : "\u2717"}
      </span>
      <span class="flex-1 text-[12px] text-[#3a3a3a]">{label}</span>
      <span
        class="font-mono text-[11px] font-semibold"
        style={{ color: valueColor }}
      >
        {value}
      </span>
    </div>
  );
}

function ExpandableChunk({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const sanitized = stripInlineCitations(text);
  const isLong = sanitized.length > CHUNK_COLLAPSE_CHARS;
  const collapsed = isLong && !expanded;

  return (
    <div>
      <div
        class="relative py-[14px] px-[15px] rounded-[11px] text-[12.5px] leading-[1.7] text-[#3a3a3a]"
        style={{
          background: "rgba(226,0,26,0.04)",
          border: "1px solid rgba(226,0,26,0.15)",
          borderLeft: "3px solid #E2001A",
          maxHeight: collapsed ? "120px" : "none",
          overflow: collapsed ? "hidden" : "visible",
        }}
      >
        <div class="jv-chunk-md">
          <Markdown remarkPlugins={[remarkGfm]}>{sanitized}</Markdown>
        </div>
        {collapsed && (
          <div
            class="absolute bottom-0 left-0 right-0 h-10 pointer-events-none"
            style={{
              background:
                "linear-gradient(transparent, rgba(226,0,26,0.04))",
            }}
          />
        )}
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          class="mt-2 flex items-center gap-1 text-[11px] font-semibold text-primary hover:text-primary-hover cursor-pointer bg-transparent border-none p-0 transition-colors"
        >
          {expanded ? (
            <>Weniger anzeigen <ChevronUp size={13} strokeWidth={2} /></>
          ) : (
            <>Mehr anzeigen <ChevronDown size={13} strokeWidth={2} /></>
          )}
        </button>
      )}
    </div>
  );
}

export function Inspector() {
  const source = selectedSource.value;
  const msg = selectedMessage.value;

  return (
    <div class="w-[400px] shrink-0 flex flex-col bg-surface border-l border-border overflow-y-auto jv-scroll">
      {/* Header */}
      <div class="flex items-center justify-between py-4 px-[18px] border-b border-border/70 sticky top-0 bg-surface z-10">
        <span class="font-mono text-[10px] font-semibold tracking-[0.16em] uppercase text-text-faint">
          Beleg-Inspektor
        </span>
        {source && (
          <span class="inline-flex items-center gap-[6px] text-[12px] font-semibold text-text-body">
            <span class="inline-flex items-center justify-center w-[18px] h-[18px] rounded-full bg-primary text-white font-mono text-[10px] font-semibold">
              {selectedSourceId.value?.replace("S", "")}
            </span>
            ausgewaehlt
          </span>
        )}
      </div>

      {/* Content */}
      <div class="p-[18px]">
        {!source ? (
          <div class="flex flex-col items-center justify-center py-16 text-center">
            <FileText size={32} strokeWidth={1.2} class="text-text-ghost mb-3" />
            <p class="text-[13px] text-text-faint">
              Klicke auf einen Zitat-Marker in der Antwort, um den Beleg hier anzuzeigen.
            </p>
          </div>
        ) : (
          <>
            {/* Document Card */}
            <div class="flex gap-3">
              <div
                class="w-10 h-10 shrink-0 rounded-[10px] flex items-center justify-center"
                style={{
                  background: "rgba(226,0,26,0.1)",
                  color: "#E2001A",
                }}
              >
                <FileText size={20} strokeWidth={1.7} />
              </div>
              <div>
                <div class="text-[14px] font-semibold text-[#161616] leading-[1.4]">
                  {source.titel}
                </div>
                <div class="font-mono text-[10px] font-medium text-text-ghost mt-[6px] leading-[1.4]">
                  {source.datei || source.breadcrumb}
                </div>
              </div>
            </div>

            {/* Metadata Table */}
            <div
              class="mt-[18px] rounded-xl bg-panel-1 overflow-hidden"
              style={{ border: "1px solid rgba(0,0,0,0.08)" }}
            >
              <div class="font-mono text-[9px] font-semibold tracking-[0.14em] uppercase text-text-ghost py-[11px] px-[13px] pb-2">
                Facetten · Metadaten
              </div>
              <div class="grid" style={{ gridTemplateColumns: "132px 1fr" }}>
                {META_FIELDS.map((field) => {
                  const val = (source as unknown as Record<string, unknown>)[field];
                  if (val == null || val === "") return null;
                  // Skip empty arrays
                  if (Array.isArray(val) && val.length === 0) return null;
                  // Resolve slugs to display labels
                  const display = Array.isArray(val)
                    ? displayValues(field, val as string[])
                    : typeof val === "number"
                      ? String(val)
                      : displayValue(field, String(val));
                  if (!display) return null;
                  return (
                    <MetadataRow key={field} field={field} value={display} />
                  );
                })}
                {source.page != null && (
                  <MetadataRow field="page" value={`S. ${source.page}`} />
                )}
              </div>
            </div>

            {/* Expandable Chunk */}
            <div class="mt-4">
              <div class="flex items-center justify-between mb-2">
                <span class="font-mono text-[9px] font-semibold tracking-[0.14em] uppercase text-text-ghost">
                  Chunk · vollstaendig
                </span>
                <span class="font-mono text-[9px] font-medium text-text-pale">
                  {source.page != null && `S. ${source.page} · `}
                  Score {source.score.toFixed(4)}
                </span>
              </div>
              <ExpandableChunk text={source.snippet} />
              {source.breadcrumb && (
                <div class="mt-2 font-mono text-[10px] font-medium leading-[1.5] text-text-ghost">
                  {source.breadcrumb}
                </div>
              )}
            </div>

            {/* Anti-Hallucination Stack */}
            {msg && (
              <div class="mt-[18px]">
                <div class="font-mono text-[9px] font-semibold tracking-[0.14em] uppercase text-text-ghost mb-[10px]">
                  Anti-Halluzination · mehrstufig
                </div>
                <div class="flex flex-col gap-2">
                  <AntiHallucinationCard
                    label="Confidence-Gate"
                    value={confidenceFromString(msg.confidence).label}
                    valueColor={confidenceFromString(msg.confidence).color}
                  />
                  <AntiHallucinationCard
                    label="Citation-Enforcement"
                    value={
                      msg.citationsValid != null
                        ? `${msg.citationsValid}/${(msg.citationsValid ?? 0) + (msg.citationsInvalid ?? 0)} belegt`
                        : "—"
                    }
                    valueColor="#8a877f"
                  />
                  {(() => {
                    const threshold = msg.groundingThreshold ?? 0.5;
                    const passed = msg.groundingScore != null && msg.groundingScore >= threshold;
                    return (
                      <AntiHallucinationCard
                        label="Grounding · Faithfulness"
                        value={
                          msg.groundingScore != null
                            ? msg.groundingScore.toFixed(2)
                            : "—"
                        }
                        valueColor={
                          msg.groundingScore != null
                            ? (passed ? "#2f9e44" : "#f0603a")
                            : "#8a877f"
                        }
                        passed={passed}
                      />
                    );
                  })()}
                  <AntiHallucinationCard
                    label="Quelle-Whitelist"
                    value={source.doc_type || "—"}
                    valueColor="#8a877f"
                  />
                </div>
              </div>
            )}

            {/* Open Source Button */}
            {(source.url || source.datei) && (
              <a
                href={source.url || `#${source.datei}`}
                target="_blank"
                rel="noopener noreferrer"
                class="mt-[18px] w-full h-[42px] rounded-[11px] bg-primary text-white text-[13px] font-semibold flex items-center justify-center gap-2 no-underline hover:bg-primary-hover transition-colors"
                style={{
                  boxShadow: "0 6px 18px -6px rgba(226,0,26,0.6)",
                }}
              >
                Quelle oeffnen <ExternalLink size={14} strokeWidth={2} />
              </a>
            )}
          </>
        )}
      </div>
    </div>
  );
}
