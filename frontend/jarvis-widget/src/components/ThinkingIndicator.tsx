/** Animated thinking indicator shown while the agent is processing. */

export function ThinkingIndicator() {
  return (
    <div class="flex gap-3">
      <img
        src="/MDZ_Icon.jpg"
        alt="KI Fabrik Scout"
        class="w-[30px] h-[30px] rounded-[9px] shrink-0 object-cover"
        style={{ boxShadow: "0 0 0 1px rgba(226,0,26,0.25)" }}
      />
      <div
        class="py-3 px-4 flex items-center gap-[6px]"
        style={{
          borderRadius: "14px",
          borderTopLeftRadius: "5px",
          border: "1px solid rgba(0,0,0,0.08)",
          background: "#ffffff",
          boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
        }}
      >
        <span class="thinking-dot" style={{ animationDelay: "0ms" }} />
        <span class="thinking-dot" style={{ animationDelay: "200ms" }} />
        <span class="thinking-dot" style={{ animationDelay: "400ms" }} />
      </div>
    </div>
  );
}
