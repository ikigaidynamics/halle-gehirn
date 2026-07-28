import { useEffect } from "preact/hooks";
import { signal } from "@preact/signals";
import { bestandData, bestandLoading, bestandError, loadBestand, removeDokument } from "../state/store";
import { ChunkViewer, openChunkViewer } from "./ChunkViewer";

// Delete confirmation state
const confirmDelete = signal<{ datei: string; titel: string; chunks: number } | null>(null);
const deleting = signal(false);
const deleteError = signal<string | null>(null);

export function BestandTab() {
  useEffect(() => {
    if (!bestandData.value) loadBestand();
  }, []);

  if (bestandLoading.value) {
    return (
      <div class="flex items-center justify-center py-20 text-text-muted text-[14px]">
        Lade Bestand...
      </div>
    );
  }

  if (bestandError.value) {
    return (
      <div class="p-6">
        <div class="p-4 rounded-lg bg-[rgba(240,96,58,0.08)] border border-[rgba(240,96,58,0.28)] text-[13px] text-[#c0392b]">
          Fehler: {bestandError.value}
        </div>
      </div>
    );
  }

  const data = bestandData.value;
  if (!data) return null;

  async function doDelete() {
    const target = confirmDelete.value;
    if (!target) return;
    deleting.value = true;
    deleteError.value = null;
    try {
      await removeDokument(target.datei, true);
      confirmDelete.value = null;
    } catch (err) {
      deleteError.value = err instanceof Error ? err.message : String(err);
    } finally {
      deleting.value = false;
    }
  }

  return (
    <div class="flex gap-6 p-6 h-full overflow-hidden">
      {/* Main: Document Table */}
      <div class="flex-1 min-w-0 flex flex-col">
        <h2 class="text-[15px] font-bold text-text-primary mb-4">
          Gespeicherte Dokumente
        </h2>
        <div class="flex-1 overflow-auto jv-scroll rounded-lg border border-border bg-surface">
          <table class="w-full text-[13px]">
            <thead>
              <tr class="bg-panel-3 text-text-secondary text-left">
                <th class="py-[10px] px-[14px] font-semibold">Titel</th>
                <th class="py-[10px] px-[14px] font-semibold w-[150px]">Dokumenttyp</th>
                <th class="py-[10px] px-[14px] font-semibold w-[150px]">Bereich</th>
                <th class="py-[10px] px-[14px] font-semibold w-[80px] text-right">Chunks</th>
                <th class="py-[10px] px-[14px] font-semibold w-[90px] text-center">Status</th>
                <th class="py-[10px] px-[14px] font-semibold w-[70px]" />
              </tr>
            </thead>
            <tbody>
              {data.manifest_entries.map((entry) => {
                const indexed = data.indexed_docs.find(
                  (d) => d.datei === entry.datei,
                );
                const chunks = indexed?.chunk_count ?? 0;

                return (
                  <tr
                    key={entry.datei}
                    class="border-t border-border-light hover:bg-panel-1 transition-colors"
                  >
                    <td class="py-[10px] px-[14px]">
                      {entry.is_indexed ? (
                        <button
                          onClick={() => openChunkViewer(entry.datei)}
                          class="block w-full text-left bg-transparent border-none p-0 cursor-pointer group"
                        >
                          <div class="font-medium text-text-primary truncate group-hover:text-[#E2001A] transition-colors">
                            {entry.titel}
                          </div>
                          <div class="text-[11px] text-text-muted font-mono truncate mt-[2px]">
                            {entry.datei}
                          </div>
                        </button>
                      ) : (
                        <div>
                          <div class="font-medium text-text-primary truncate">
                            {entry.titel}
                          </div>
                          <div class="text-[11px] text-text-muted font-mono truncate mt-[2px]">
                            {entry.datei}
                          </div>
                        </div>
                      )}
                    </td>
                    <td class="py-[10px] px-[14px] text-text-secondary">
                      {entry.doc_type_label}
                    </td>
                    <td class="py-[10px] px-[14px] text-text-secondary">
                      {entry.bereich_labels.join(", ")}
                    </td>
                    <td class="py-[10px] px-[14px] text-right font-mono text-text-secondary">
                      {chunks > 0 ? chunks : "\u2014"}
                    </td>
                    <td class="py-[10px] px-[14px] text-center">
                      <span
                        class="inline-flex items-center gap-[5px] py-[3px] px-[8px] rounded-full text-[11px] font-medium"
                        style={{
                          background: entry.is_indexed
                            ? "rgba(47,158,68,0.10)"
                            : "rgba(227,160,8,0.10)",
                          color: entry.is_indexed ? "#2f9e44" : "#e3a008",
                        }}
                      >
                        <span
                          class="w-[5px] h-[5px] rounded-full"
                          style={{
                            background: entry.is_indexed
                              ? "#2f9e44"
                              : "#e3a008",
                          }}
                        />
                        {entry.is_indexed ? "Indexiert" : "Pending"}
                      </span>
                    </td>
                    <td class="py-[10px] px-[14px]">
                      <button
                        onClick={() => {
                          confirmDelete.value = {
                            datei: entry.datei,
                            titel: entry.titel,
                            chunks,
                          };
                          deleteError.value = null;
                        }}
                        class="py-[4px] px-[8px] rounded-md text-[11px] font-medium border cursor-pointer transition-colors bg-transparent"
                        style={{
                          borderColor: "rgba(240,96,58,0.3)",
                          color: "#f0603a",
                        }}
                      >
                        Entfernen
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Sidebar: Collection Stats */}
      <div class="w-[260px] shrink-0 flex flex-col gap-4">
        {/* Collection Card */}
        <div class="p-[18px] rounded-xl bg-surface border border-border">
          <div class="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-3">
            Collection
          </div>
          <div class="text-[28px] font-bold text-text-primary leading-none">
            {data.total_chunks}
          </div>
          <div class="text-[12px] text-text-muted mt-1">
            Chunks in halle_wissen
          </div>
          <div class="mt-4 pt-3 border-t border-border-light flex flex-col gap-[6px]">
            <div class="flex justify-between text-[12px]">
              <span class="text-text-muted">Dokumente (Manifest)</span>
              <span class="font-mono text-text-secondary font-medium">
                {data.manifest_entries.length}
              </span>
            </div>
            <div class="flex justify-between text-[12px]">
              <span class="text-text-muted">Indexiert (Qdrant)</span>
              <span class="font-mono text-text-secondary font-medium">
                {data.indexed_docs.length}
              </span>
            </div>
            <div class="flex justify-between text-[12px]">
              <span class="text-text-muted">Waisen</span>
              <span class="font-mono text-text-secondary font-medium">
                {data.indexed_docs.filter((d) => !d.in_manifest).length}
              </span>
            </div>
          </div>
        </div>

        {/* Reload Button */}
        <button
          onClick={() => loadBestand()}
          disabled={bestandLoading.value}
          class="w-full py-[10px] rounded-lg text-[13px] font-semibold text-white cursor-pointer border-none"
          style={{
            background: bestandLoading.value ? "#ccc" : "#E2001A",
          }}
        >
          {bestandLoading.value ? "Lade..." : "Aktualisieren"}
        </button>
      </div>

      {/* Chunk Viewer Overlay */}
      <ChunkViewer />

      {/* Delete Confirmation Dialog */}
      {confirmDelete.value && (
        <div
          class="fixed inset-0 flex items-center justify-center z-50"
          style={{ background: "rgba(0,0,0,0.35)" }}
          onClick={(e) => {
            if (e.target === e.currentTarget) confirmDelete.value = null;
          }}
        >
          <div class="bg-surface rounded-xl p-6 shadow-lg w-[420px] border border-border">
            <h3 class="text-[15px] font-bold text-text-primary mb-3">
              Dokument entfernen?
            </h3>
            <p class="text-[13px] text-text-body mb-2">
              <span class="font-semibold">{confirmDelete.value.titel}</span>
            </p>
            <p class="text-[12px] text-text-muted font-mono mb-3">
              {confirmDelete.value.datei}
            </p>
            <div class="p-3 rounded-lg mb-4 text-[12px]"
              style={{
                background: "rgba(240,96,58,0.06)",
                border: "1px solid rgba(240,96,58,0.2)",
                color: "#c0392b",
              }}>
              {confirmDelete.value.chunks > 0
                ? `${confirmDelete.value.chunks} Chunk${confirmDelete.value.chunks !== 1 ? "s" : ""} werden aus Qdrant geloescht. Manifest-Eintrag und Datei werden entfernt.`
                : "Manifest-Eintrag und Datei werden entfernt (keine Chunks indexiert)."}
            </div>

            {deleteError.value && (
              <div class="p-3 rounded-lg mb-3 text-[12px]"
                style={{ background: "rgba(240,96,58,0.08)", border: "1px solid rgba(240,96,58,0.28)", color: "#c0392b" }}>
                {deleteError.value}
              </div>
            )}

            <div class="flex gap-3 justify-end">
              <button
                onClick={() => { confirmDelete.value = null; deleteError.value = null; }}
                class="py-[8px] px-[16px] rounded-lg text-[13px] font-medium border cursor-pointer bg-transparent"
                style={{ borderColor: "rgba(0,0,0,0.12)", color: "#555" }}
              >
                Abbrechen
              </button>
              <button
                onClick={doDelete}
                disabled={deleting.value}
                class="py-[8px] px-[16px] rounded-lg text-[13px] font-semibold text-white border-none cursor-pointer"
                style={{ background: deleting.value ? "#ccc" : "#f0603a" }}
              >
                {deleting.value ? "Loeschen..." : "Endgueltig entfernen"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
