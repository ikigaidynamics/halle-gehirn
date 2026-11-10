import { readyState } from "../state/store";

export function Topbar() {
  const ready = readyState.value;
  const allOk = ready?.qdrant && ready?.ollama;

  return (
    <div class="flex items-center justify-between h-[60px] px-[22px] bg-surface border-b border-border">
      {/* Left: Logo + Title */}
      <div class="flex items-center gap-3">
        <img
          src="/MDZ_Icon.jpg"
          alt="MDZ"
          class="w-[34px] h-[34px] rounded-[9px] object-cover"
        />
        <span class="text-[16px] font-bold text-text-primary tracking-[-0.01em]">
          KI Fabrik Scout Wissensbestand
        </span>
      </div>

      {/* Right: Status badges */}
      <div class="flex items-center gap-[10px]">
        {/* Qdrant Status */}
        <div
          class="flex items-center gap-[7px] py-[7px] px-[11px] rounded-lg"
          style={{
            background: ready?.qdrant
              ? "rgba(47,158,68,0.08)"
              : "rgba(240,96,58,0.08)",
            border: `1px solid ${
              ready?.qdrant
                ? "rgba(47,158,68,0.28)"
                : "rgba(240,96,58,0.28)"
            }`,
          }}
        >
          <span
            class="w-[7px] h-[7px] rounded-full"
            style={{
              background: ready?.qdrant ? "#2f9e44" : "#f0603a",
              boxShadow: ready?.qdrant
                ? "0 0 8px rgba(47,158,68,0.5)"
                : "0 0 8px rgba(240,96,58,0.5)",
            }}
          />
          <span
            class="font-mono text-[11px] font-medium leading-none"
            style={{ color: ready?.qdrant ? "#2f9e44" : "#f0603a" }}
          >
            Qdrant
          </span>
        </div>

        {/* Ollama Status */}
        <div
          class="flex items-center gap-[7px] py-[7px] px-[11px] rounded-lg"
          style={{
            background: ready?.ollama
              ? "rgba(47,158,68,0.08)"
              : "rgba(240,96,58,0.08)",
            border: `1px solid ${
              ready?.ollama
                ? "rgba(47,158,68,0.28)"
                : "rgba(240,96,58,0.28)"
            }`,
          }}
        >
          <span
            class="w-[7px] h-[7px] rounded-full"
            style={{
              background: ready?.ollama ? "#2f9e44" : "#f0603a",
              boxShadow: ready?.ollama
                ? "0 0 8px rgba(47,158,68,0.5)"
                : "0 0 8px rgba(240,96,58,0.5)",
            }}
          />
          <span
            class="font-mono text-[11px] font-medium leading-none"
            style={{ color: ready?.ollama ? "#2f9e44" : "#f0603a" }}
          >
            Ollama
          </span>
        </div>

        {/* Overall status */}
        <span
          class="py-[7px] px-[10px] rounded-lg border text-[11px] font-semibold"
          style={{
            background: allOk ? "rgba(47,158,68,0.08)" : "rgba(0,0,0,0.02)",
            borderColor: allOk ? "rgba(47,158,68,0.28)" : "rgba(0,0,0,0.08)",
            color: allOk ? "#2f9e44" : "#8a877f",
          }}
        >
          {allOk ? "On-Prem" : "Warte..."}
        </span>
      </div>
    </div>
  );
}
