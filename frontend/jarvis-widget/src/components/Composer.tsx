import { useState } from "preact/hooks";
import { ArrowUp } from "lucide-preact";
import { sendMessage, streaming } from "../state/store";

export function Composer() {
  const [input, setInput] = useState("");

  const handleSubmit = () => {
    const q = input.trim();
    if (!q || streaming.value) return;
    setInput("");
    sendMessage(q);
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div class="py-[14px] px-[26px] pb-[18px] border-t border-border/70 bg-panel-2">
      <div class="max-w-[660px] mx-auto">
        <div
          class="flex items-center gap-[10px] rounded-[15px] bg-surface px-3 py-[10px]"
          style={{
            border: "1px solid rgba(0,0,0,0.12)",
            boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
          }}
        >
          {/* Attach placeholder */}
          <span class="w-[30px] h-[30px] rounded-lg bg-panel-5 flex items-center justify-center text-[15px] text-text-muted shrink-0">
            +
          </span>

          {/* Input */}
          <input
            type="text"
            value={input}
            onInput={(e) => setInput((e.target as HTMLInputElement).value)}
            onKeyDown={handleKeyDown}
            placeholder="Folgefrage stellen..."
            disabled={streaming.value}
            class="flex-1 text-[14px] text-text-body placeholder:text-text-faint bg-transparent border-none outline-none"
          />

          {/* Send */}
          <button
            onClick={handleSubmit}
            disabled={streaming.value || !input.trim()}
            class="w-9 h-9 rounded-[10px] bg-primary text-white flex items-center justify-center border-none cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-primary-hover transition-colors"
            style={{ boxShadow: "0 6px 18px -6px rgba(226,0,26,0.6)" }}
          >
            <ArrowUp size={15} strokeWidth={2.5} />
          </button>
        </div>

        <p class="mt-[9px] text-center font-mono text-[10.5px] font-medium leading-[1.4] text-text-ghost">
          Multi-Turn-Kontext (Fenster 5) · quellenbelegt · On-Prem · keine Cloud
        </p>
      </div>
    </div>
  );
}
