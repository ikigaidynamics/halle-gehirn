/** Global state via Preact Signals. */

import { signal, computed } from "@preact/signals";
import { streamChat, checkHealth, type Source, type DoneEvent } from "../api/chat";

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
}

// ── Signals ──

export const messages = signal<Message[]>([]);
export const streaming = signal(false);
export const streamBuffer = signal("");
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

  abortController = streamChat(query, sessionId.value, {
    onToken(token: string) {
      streamBuffer.value += token;
    },
    onDone(event: DoneEvent) {
      const finalContent = event.final_answer || streamBuffer.value;
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
        },
      ];
      streaming.value = false;
      streamBuffer.value = "";
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
      abortController = null;
    },
  });
}

export function cancelStream(): void {
  abortController?.abort();
  streaming.value = false;
  streamBuffer.value = "";
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
