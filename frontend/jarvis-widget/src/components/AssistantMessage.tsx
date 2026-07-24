import type { JSX } from "preact";
import type { Source } from "../api/chat";
import { confidenceFromString } from "../lib/confidence";
import { markdownToHtml } from "../lib/markdown";
import { selectSource, selectedSourceId } from "../state/store";

interface Props {
  content: string;
  sources: Source[];
  confidence: string;
  groundingScore?: number;
  isStreaming?: boolean;
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
    const isActive = selectedSourceId.value === sourceId;
    const exists = sources.some((s) => s.id === sourceId);

    if (exists) {
      parts.push(
        <button
          onClick={() => selectSource(sourceId)}
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

/** Build source labels with "ebenda" for repeated titles. */
function buildSourceLabels(sources: Source[]): { id: string; label: string }[] {
  const seen = new Map<string, number>(); // title → first occurrence index
  return sources.map((s) => {
    const num = s.id.replace("S", "");
    const title = s.titel || s.datei || `Quelle ${num}`;
    const prevIdx = seen.get(title);
    if (prevIdx !== undefined) {
      // Same title seen before — show "ebenda" with reference to first
      return { id: s.id, label: `${num} ebenda` };
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
}: Props) {
  const conf = confidence ? confidenceFromString(confidence) : null;
  const sourceLabels = !isStreaming && sources.length > 0
    ? buildSourceLabels(sources)
    : [];

  return (
    <div class="flex gap-3">
      {/* Jarvis Avatar */}
      <img
        src="/MDZ_Icon.jpg"
        alt="Jarvis"
        class="w-[30px] h-[30px] rounded-[9px] shrink-0 object-cover"
        style={{ boxShadow: "0 0 0 1px rgba(226,0,26,0.25)" }}
      />

      <div class="min-w-0">
        {/* Confidence Ampel (shown after streaming) */}
        {conf && !isStreaming && (
          <div
            class="flex items-center gap-[7px] py-[5px] px-[11px] rounded-lg w-fit mb-[9px]"
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
              renderContentWithCitations(content, sources)
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
                  const isActive = selectedSourceId.value === id;
                  const num = id.replace("S", "");
                  const isEbenda = label.includes("ebenda");
                  return (
                    <button
                      key={id}
                      onClick={() => selectSource(id)}
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
                        style={{
                          color: isEbenda ? "#8a877f" : "#555",
                          fontStyle: isEbenda ? "italic" : "normal",
                        }}
                      >
                        {isEbenda ? "ebenda" : label.slice(num.length + 1)}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
