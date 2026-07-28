import { useEffect } from "preact/hooks";
import { Topbar } from "./components/Topbar";
import { BestandTab } from "./components/BestandTab";
import { NeuDokumentTab } from "./components/NeuDokumentTab";
import { IndexierenTab } from "./components/IndexierenTab";
import { activeTab, refreshReady } from "./state/store";

const TABS = [
  { key: "bestand" as const, label: "Bestand" },
  { key: "neu" as const, label: "Neues Dokument" },
  { key: "indexieren" as const, label: "Indexieren" },
];

export function App() {
  useEffect(() => {
    refreshReady();
    const interval = setInterval(refreshReady, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div class="h-screen flex flex-col bg-page">
      <Topbar />

      {/* Tab Bar */}
      <div class="flex items-center gap-0 px-[22px] bg-surface border-b border-border">
        {TABS.map((tab) => {
          const active = activeTab.value === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => (activeTab.value = tab.key)}
              class="relative py-[12px] px-[16px] text-[13px] font-medium border-none bg-transparent cursor-pointer transition-colors"
              style={{
                color: active ? "#E2001A" : "#8a877f",
              }}
            >
              {tab.label}
              {active && (
                <span
                  class="absolute bottom-0 left-[16px] right-[16px] h-[2px]"
                  style={{ background: "#E2001A" }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div class="flex-1 min-h-0 overflow-hidden">
        {activeTab.value === "bestand" && <BestandTab />}
        {activeTab.value === "neu" && <NeuDokumentTab />}
        {activeTab.value === "indexieren" && <IndexierenTab />}
      </div>
    </div>
  );
}
