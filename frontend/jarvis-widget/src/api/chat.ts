/** SSE client for /chat/stream and health endpoints. */

export interface Source {
  id: string;
  titel: string;
  url: string | null;
  datei: string;
  snippet: string;
  page: number | null;
  score: number;
  doc_type: string;
  breadcrumb: string;
  figure_refs: string[];
  figure_captions: string[];
  bereich: string[];
  herkunft: string;
  quelltyp: string;
  vertraulichkeit: string;
  status: string;
  jahr: number | null;
  thema: string[];
  anlage: string[];
  projekt: string[];
  ansprechperson: string[];
  autor: string[];
  grad: string;
}

export interface DoneEvent {
  confidence: string;
  sources: Source[];
  final_answer: string;
  latency_ms: number;
  grounding_score?: number;
  grounded?: boolean;
  grounding_threshold?: number;
  citations_valid?: number;
  citations_invalid?: number;
  pii_redacted?: boolean;
}

export interface StreamCallbacks {
  onToken: (token: string) => void;
  onDone: (event: DoneEvent) => void;
  onError: (error: Error) => void;
}

/**
 * Streams a chat response via SSE (POST /chat/stream).
 * Returns an AbortController to cancel the request.
 */
export function streamChat(
  query: string,
  sessionId: string,
  callbacks: StreamCallbacks,
  filters?: Record<string, string | string[]>,
): AbortController {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          session_id: sessionId,
          filters: filters ?? null,
        }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const json = trimmed.slice(6);
          try {
            const event = JSON.parse(json);
            if (event.type === "token") {
              callbacks.onToken(event.content);
            } else if (event.type === "done") {
              callbacks.onDone(event as DoneEvent);
            }
          } catch {
            // skip malformed SSE lines
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError(err as Error);
      }
    }
  })();

  return controller;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const resp = await fetch("/health");
    const data = await resp.json();
    return data.status === "ok";
  } catch {
    return false;
  }
}

export interface ReadyStatus {
  status: string;
  qdrant: boolean;
  ollama: boolean;
}

export async function checkReady(): Promise<ReadyStatus> {
  try {
    const resp = await fetch("/ready");
    return await resp.json();
  } catch {
    return { status: "not_ready", qdrant: false, ollama: false };
  }
}
