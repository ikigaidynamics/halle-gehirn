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
export const sessionId = signal(crypto.randomUUID());
export const healthOk = signal(false);
export const modelName = signal("qwen3:8b");

/** The currently selected source object (derived). */
export const selectedSource = computed<Source | null>(() => {
  const id = selectedSourceId.value;
  if (!id) return null;
  for (const msg of messages.value) {
    const found = msg.sources.find((s) => s.id === id);
    if (found) return found;
  }
  return null;
});

/** The message that owns the currently selected source (for anti-hallucination data). */
export const selectedMessage = computed<Message | null>(() => {
  const id = selectedSourceId.value;
  if (!id) return null;
  for (const msg of messages.value) {
    if (msg.sources.some((s) => s.id === id)) return msg;
  }
  return null;
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
  sessionId.value = crypto.randomUUID();
}

export function selectSource(id: string): void {
  selectedSourceId.value = selectedSourceId.value === id ? null : id;
}

export async function refreshHealth(): Promise<void> {
  healthOk.value = await checkHealth();
}
