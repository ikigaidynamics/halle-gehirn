export function Footer() {
  return (
    <div class="flex items-center justify-between h-[58px] px-6 bg-panel-4 border-t border-border">
      {/* Left: Spreeland logo + text */}
      <div class="flex items-center gap-[14px]">
        <img
          src="/MD_zentrum_Spreeland.png"
          alt="Mittelstand-Digital Zentrum Spreeland"
          class="h-[34px] w-auto"
        />
        <span class="text-[11px] text-[#777] max-w-[300px] leading-[1.4]">
          Ein Angebot des Mittelstand-Digital Zentrums Spreeland
        </span>
      </div>

    </div>
  );
}
