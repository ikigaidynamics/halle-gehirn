/** Global state via Preact Signals. */

import { signal, computed } from "@preact/signals";
import { streamChat, checkHealth, type Source, type DoneEvent, type LatencyStats } from "../api/chat";

export interface Message {
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  confidence: string;
  groundingScore?: number;
  grounded?: boolean;
  groundingThreshold?: number;
  citationsValid?: number;
  citationsInvalid?: number;
  latencyMs?: number;
  stats?: LatencyStats;
}

// ── Signals ──

export const messages = signal<Message[]>([]);
export const streaming = signal(false);
export const streamBuffer = signal("");
export const streamStartTime = signal<number>(0);
export const selectedSourceId = signal<string | null>(null);
export const selectedMsgIdx = signal<number>(-1);
export const sessionId = signal(crypto.randomUUID());
export const healthOk = signal(false);
export const modelName = signal("qwen3:8b");

/** The currently selected source object — scoped to the selected message. */
export const selectedSource = computed<Source | null>(() => {
  const id = selectedSourceId.value;
  const idx = selectedMsgIdx.value;
  if (!id || idx < 0) return null;
  const msg = messages.value[idx];
  if (!msg) return null;
  return msg.sources.find((s) => s.id === id) ?? null;
});

/** The message that owns the currently selected source. */
export const selectedMessage = computed<Message | null>(() => {
  const idx = selectedMsgIdx.value;
  if (idx < 0) return null;
  return messages.value[idx] ?? null;
});

let abortController: AbortController | null = null;

export function sendMessage(query: string): void {
  if (streaming.value || !query.trim()) return;

  // Add user message
  messages.value = [
    ...messages.value,
    { role: "user", content: query, sources: [], confidence: "" },
  ];

  streaming.value = true;
  streamBuffer.value = "";
  streamStartTime.value = Date.now();

  // Timing-Logs
  const requestStart = Date.now();
  let firstTokenTime = 0;
  let tokenCount = 0;
  console.log("%c🚀 Request gestartet", "color: #3b82f6; font-weight: bold;", new Date().toLocaleTimeString());

  abortController = streamChat(query, sessionId.value, {
    onToken(token: string) {
      tokenCount++;
      if (tokenCount === 1) {
        firstTokenTime = Date.now();
        const ttft = firstTokenTime - requestStart;
        console.log(
          `%c⚡ Erstes Token nach ${ttft} ms (TTFT)`,
          ttft > 5000 ? "color: #dc2626; font-weight: bold;" : "color: #10b981; font-weight: bold;"
        );
        if (ttft > 5000) {
          console.warn("⚠️ TTFT > 5s - Bottleneck vor der Generierung (Embedding/Rewrite/Rerank/Netzwerk)");
        }
      }
      streamBuffer.value += token;
    },
    onDone(event: DoneEvent) {
      const finalContent = event.final_answer || streamBuffer.value;
      const totalTime = Date.now() - requestStart;
      const generationTime = firstTokenTime ? Date.now() - firstTokenTime : 0;

      // Timing-Zusammenfassung
      console.log("%c✅ Antwort komplett", "color: #10b981; font-weight: bold;", new Date().toLocaleTimeString());
      console.group("%c⏱️ Timing-Übersicht", "font-weight: bold;");
      console.log(`Request → Erstes Token (TTFT): ${firstTokenTime ? firstTokenTime - requestStart : "?"} ms`);
      console.log(`Erstes Token → Fertig:         ${generationTime} ms`);
      console.log(`Tokens empfangen:              ${tokenCount}`);
      console.log(`Tokens/Sekunde:                ${generationTime > 0 ? (tokenCount / (generationTime / 1000)).toFixed(1) : "?"}`);
      console.log(`Gesamtzeit (Frontend):         ${totalTime} ms`);
      console.groupEnd();

      // Detaillierte Console-Logs
      const stats = event.stats;
      if (stats) {
        console.group("%c📊 Pipeline-Statistik", "font-weight: bold; color: #3b82f6;");
        console.log("%c┌─────────────────────────────────────────┐", "color: #888;");
        if (stats.rewrite_ms > 0) {
          console.log(`%c│ Query-Rewrite:    %c${stats.rewrite_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #8b5cf6; font-weight: bold;");
        }
        console.log(`%c│ Embedding:        %c${stats.embed_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #3b82f6; font-weight: bold;");
        console.log(`%c│ Qdrant-Suche:     %c${stats.search_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #10b981; font-weight: bold;");
        const rerankColor = stats.rerank_ms > 1000 ? "#dc2626" : "#f59e0b";
        console.log(`%c│ Reranking:        %c${stats.rerank_ms.toFixed(0).padStart(8)} ms` + (stats.rerank_ms > 1000 ? " ⚠️ BOTTLENECK" : ""), "color: #888;", `color: ${rerankColor}; font-weight: bold;`);
        console.log(`%c│ LLM-Generierung:  %c${stats.generate_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #6366f1; font-weight: bold;");
        console.log("%c├─────────────────────────────────────────┤", "color: #888;");
        console.log(`%c│ Pipeline gesamt:  %c${stats.total_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #333; font-weight: bold;");
        console.log(`%c│ End-to-End:       %c${event.latency_ms.toFixed(0).padStart(8)} ms`, "color: #888;", "color: #333; font-weight: bold;");
        console.log("%c└─────────────────────────────────────────┘", "color: #888;");

        // Bottleneck-Analyse
        const total = stats.total_ms || 1;
        const stages = [
          { name: "Rewrite", ms: stats.rewrite_ms },
          { name: "Embedding", ms: stats.embed_ms },
          { name: "Suche", ms: stats.search_ms },
          { name: "Reranking", ms: stats.rerank_ms },
          { name: "Generation", ms: stats.generate_ms },
        ].sort((a, b) => b.ms - a.ms);

        console.log("%c🔍 Bottleneck-Analyse:", "font-weight: bold;");
        stages.forEach((s, i) => {
          const pct = ((s.ms / total) * 100).toFixed(1);
          const bar = "█".repeat(Math.round(Number(pct) / 5));
          console.log(`   ${i + 1}. ${s.name.padEnd(12)} ${pct.padStart(5)}% ${bar}`);
        });
        console.groupEnd();
      }

      messages.value = [
        ...messages.value,
        {
          role: "assistant",
          content: finalContent,
          sources: event.sources,
          confidence: event.confidence,
          groundingScore: event.grounding_score,
          grounded: event.grounded,
          groundingThreshold: event.grounding_threshold,
          citationsValid: event.citations_valid,
          citationsInvalid: event.citations_invalid,
          latencyMs: event.latency_ms,
          stats: event.stats,
        },
      ];
      streaming.value = false;
      streamBuffer.value = "";
      streamStartTime.value = 0;
      abortController = null;
    },
    onError(err: Error) {
      console.error("Stream error:", err);
      messages.value = [
        ...messages.value,
        {
          role: "assistant",
          content: "Verbindungsfehler — bitte erneut versuchen.",
          sources: [],
          confidence: "rot",
        },
      ];
      streaming.value = false;
      streamBuffer.value = "";
      streamStartTime.value = 0;
      abortController = null;
    },
  });
}

export function cancelStream(): void {
  abortController?.abort();
  streaming.value = false;
  streamBuffer.value = "";
  streamStartTime.value = 0;
  abortController = null;
}

export function newConversation(): void {
  cancelStream();
  messages.value = [];
  selectedSourceId.value = null;
  selectedMsgIdx.value = -1;
  sessionId.value = crypto.randomUUID();
}

export function selectSource(id: string, msgIdx: number): void {
  if (selectedSourceId.value === id && selectedMsgIdx.value === msgIdx) {
    selectedSourceId.value = null;
    selectedMsgIdx.value = -1;
  } else {
    selectedSourceId.value = id;
    selectedMsgIdx.value = msgIdx;
  }
}

export async function refreshHealth(): Promise<void> {
  healthOk.value = await checkHealth();
}
