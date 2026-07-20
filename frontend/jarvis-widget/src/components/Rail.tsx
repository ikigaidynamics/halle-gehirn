import {
  MessageSquare,
  FileText,
  BarChart3,
  Settings,
  Plus,
} from "lucide-preact";
import { newConversation } from "../state/store";

export function Rail() {
  return (
    <div class="w-[66px] shrink-0 flex flex-col items-center gap-[6px] py-4 bg-panel-1 border-r border-border/70">
      {/* New Chat */}
      <button
        onClick={newConversation}
        class="w-[42px] h-[42px] rounded-xl bg-primary flex items-center justify-center text-white cursor-pointer border-none"
        style={{ boxShadow: "0 6px 16px -6px rgba(226,0,26,0.6)" }}
        title="Neue Konversation"
      >
        <Plus size={21} strokeWidth={2.2} />
      </button>

      <div class="h-2" />

      {/* Chat (active) */}
      <button
        class="w-[42px] h-[42px] rounded-xl flex items-center justify-center cursor-pointer border-none"
        style={{
          background: "rgba(226,0,26,0.1)",
          border: "1px solid rgba(226,0,26,0.25)",
          color: "#E2001A",
        }}
        title="Chat"
      >
        <MessageSquare size={19} strokeWidth={1.8} />
      </button>

      {/* Documents */}
      <button
        class="w-[42px] h-[42px] rounded-xl flex items-center justify-center cursor-pointer border-none bg-transparent text-text-ghost"
        title="Dokumente"
      >
        <FileText size={19} strokeWidth={1.8} />
      </button>

      {/* Stats */}
      <button
        class="w-[42px] h-[42px] rounded-xl flex items-center justify-center cursor-pointer border-none bg-transparent text-text-ghost"
        title="Statistik"
      >
        <BarChart3 size={19} strokeWidth={1.8} />
      </button>

      {/* Settings (pushed to bottom) */}
      <button
        class="w-[42px] h-[42px] rounded-xl flex items-center justify-center cursor-pointer border-none bg-transparent text-text-ghost mt-auto"
        title="Einstellungen"
      >
        <Settings size={19} strokeWidth={1.8} />
      </button>
    </div>
  );
}
