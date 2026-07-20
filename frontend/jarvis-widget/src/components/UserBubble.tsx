interface Props {
  content: string;
}

export function UserBubble({ content }: Props) {
  return (
    <div class="flex flex-row-reverse gap-3">
      {/* Avatar */}
      <div class="w-[30px] h-[30px] rounded-[9px] shrink-0 flex items-center justify-center bg-panel-5 border border-border text-[10px] font-bold text-text-secondary">
        RJ
      </div>
      {/* Bubble */}
      <div
        class="py-[11px] px-[15px] text-[14px] leading-[1.6] text-[#222]"
        style={{
          borderRadius: "15px",
          borderTopRightRadius: "5px",
          background: "rgba(226,0,26,0.08)",
          border: "1px solid rgba(226,0,26,0.2)",
        }}
      >
        {content}
      </div>
    </div>
  );
}
