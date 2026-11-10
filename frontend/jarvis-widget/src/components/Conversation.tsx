import { useEffect, useRef } from "preact/hooks";
import { messages, streaming, streamBuffer, streamStartTime } from "../state/store";
import { UserBubble } from "./UserBubble";
import { AssistantMessage } from "./AssistantMessage";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { Composer } from "./Composer";

function WelcomeScreen() {
  return (
    <div class="flex flex-col items-center justify-center py-20 text-center">
      <img
        src="/MDZ_Icon.jpg"
        alt="KI Fabrik Scout"
        class="w-16 h-16 rounded-2xl object-cover mb-5"
        style={{ boxShadow: "0 0 0 2px rgba(226,0,26,0.2)" }}
      />
      <h2 class="text-[20px] font-bold text-text-primary mb-2 tracking-[-0.01em]">
        Willkommen beim KI Fabrik Scout
      </h2>
      <p class="text-[14px] text-text-faint leading-[1.6] max-w-[420px]">
        Ich bin der Wissensassistent der Modellfabrik. Stelle mir eine Frage
        zu Dokumenten, Abschlussarbeiten oder Anlagen — ich antworte
        quellenbelegt und zeige dir die Belege im Detail.
      </p>
      <div class="flex flex-wrap justify-center gap-2 mt-6">
        {[
          "Welche Sensoren eignen sich für Predictive Maintenance?",
          "Was ist der Forschungsschwerpunkt MRK?",
          "Welche Anlagen gibt es in der Modellfabrik?",
        ].map((q) => (
          <button
            key={q}
            onClick={() => {
              const input = document.querySelector<HTMLInputElement>(
                'input[placeholder]',
              );
              if (input) {
                // Set value and trigger input event
                const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                  HTMLInputElement.prototype, 'value',
                )?.set;
                nativeInputValueSetter?.call(input, q);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
              }
            }}
            class="py-2 px-3 rounded-xl text-[12.5px] text-text-body bg-surface border border-border hover:border-primary-border cursor-pointer transition-colors"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Conversation() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isEmpty = messages.value.length === 0 && !streaming.value;

  // Auto-scroll to bottom on new messages or while streaming
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages.value.length, streamBuffer.value]);

  return (
    <div class="flex-1 flex flex-col min-w-0 bg-panel-2">
      {/* Scroll area */}
      <div ref={scrollRef} class="jv-scroll flex-1 overflow-y-auto pt-[30px] px-[26px] pb-2">
        <div class="max-w-[660px] mx-auto flex flex-col gap-[22px]">
          {isEmpty && <WelcomeScreen />}

          {messages.value.map((msg, i) =>
            msg.role === "user" ? (
              <UserBubble key={i} content={msg.content} />
            ) : (
              <AssistantMessage
                key={i}
                content={msg.content}
                sources={msg.sources}
                confidence={msg.confidence}
                groundingScore={msg.groundingScore}
                latencyMs={msg.latencyMs}
                stats={msg.stats}
                msgIdx={i}
              />
            ),
          )}

          {/* Thinking indicator (before first token arrives) */}
          {streaming.value && !streamBuffer.value && (
            <ThinkingIndicator />
          )}

          {/* Streaming assistant message */}
          {streaming.value && streamBuffer.value && (
            <AssistantMessage
              content={streamBuffer.value}
              sources={[]}
              confidence=""
              isStreaming
              msgIdx={messages.value.length}
              streamStartTime={streamStartTime.value}
            />
          )}
        </div>
      </div>

      <Composer />
    </div>
  );
}
