import { healthOk, modelName } from "../state/store";

export function Topbar() {
  return (
    <div class="flex items-center justify-between h-[60px] px-[22px] bg-surface border-b border-border">
      {/* Left: Logo + Wordmark */}
      <div class="flex items-center gap-3">
        <img
          src="/MDZ_Icon.jpg"
          alt="MDZ"
          class="w-[34px] h-[34px] rounded-[9px] object-cover"
        />
        <span class="text-[16px] font-bold text-text-primary tracking-[-0.01em]">
          KI Fabrik Scout
        </span>
      </div>

      {/* Right: Badges + Avatar */}
      <div class="flex items-center gap-[10px]">
        {/* On-Prem Badge */}
        <div
          class="flex items-center gap-[7px] py-[7px] px-[11px] rounded-lg"
          style={{
            background: healthOk.value
              ? "rgba(47,158,68,0.08)"
              : "rgba(240,96,58,0.08)",
            border: `1px solid ${
              healthOk.value
                ? "rgba(47,158,68,0.28)"
                : "rgba(240,96,58,0.28)"
            }`,
          }}
        >
          <span
            class="w-[7px] h-[7px] rounded-full"
            style={{
              background: healthOk.value ? "#2f9e44" : "#f0603a",
              boxShadow: healthOk.value
                ? "0 0 8px rgba(47,158,68,0.5)"
                : "0 0 8px rgba(240,96,58,0.5)",
            }}
          />
          <span
            class="font-mono text-[11px] font-medium leading-none"
            style={{ color: healthOk.value ? "#2f9e44" : "#f0603a" }}
          >
            On-Prem · {modelName.value}
          </span>
        </div>

        {/* Compliance Chips */}
        <span class="py-[7px] px-[10px] rounded-lg bg-panel-3 border border-border text-[11px] font-semibold text-text-secondary">
          DSGVO
        </span>
        <span class="py-[7px] px-[10px] rounded-lg bg-panel-3 border border-border text-[11px] font-semibold text-text-secondary">
          EU&nbsp;AI&nbsp;Act
        </span>

        {/* User Avatar */}
        <div class="w-9 h-9 rounded-[10px] flex items-center justify-center bg-panel-5 border border-border text-[12px] font-bold text-text-secondary">
          RJ
        </div>
      </div>
    </div>
  );
}
