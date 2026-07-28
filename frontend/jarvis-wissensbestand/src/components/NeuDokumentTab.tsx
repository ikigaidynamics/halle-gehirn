import { useEffect, useRef } from "preact/hooks";
import { signal } from "@preact/signals";
import { vokabular, loadVokabular, loadBestand, activeTab } from "../state/store";
import { detectMetadata, uploadDokument, createVokabularEntry } from "../api/admin";
import type { DokumentMetadata } from "../api/types";

// ── Local signals ──
const file = signal<File | null>(null);
const detecting = signal(false);
const detectError = signal<string | null>(null);
const saving = signal(false);
const saveError = signal<string | null>(null);
const saveSuccess = signal<string | null>(null);

// Form fields
const titel = signal("");
const sorte = signal("");
const docType = signal("sonstiges");
const bereich = signal<string[]>([]);
const herkunft = signal("lehrstuhl_at");
const quelltyp = signal("primaer");
const vertraulichkeit = signal("");
const status = signal("final");
const jahr = signal<string>("");
const grad = signal("");
const thema = signal<string[]>([]);
const anlage = signal<string[]>([]);
const projekt = signal<string[]>([]);
const ansprechperson = signal<string[]>([]);
const autor = signal<string[]>([]);

// Inline vokabular creation
const showVokDialog = signal(false);
const vokFacet = signal("");
const vokSlug = signal("");
const vokLabel = signal("");
const vokError = signal<string | null>(null);
const vokSaving = signal(false);

const ACCEPTED = ".pdf,.docx,.pptx,.xlsx,.md,.txt";

function resetForm() {
  file.value = null;
  detecting.value = false;
  detectError.value = null;
  saveError.value = null;
  titel.value = "";
  sorte.value = "";
  docType.value = "sonstiges";
  bereich.value = [];
  herkunft.value = "lehrstuhl_at";
  quelltyp.value = "primaer";
  vertraulichkeit.value = "";
  status.value = "final";
  jahr.value = "";
  grad.value = "";
  thema.value = [];
  anlage.value = [];
  projekt.value = [];
  ansprechperson.value = [];
  autor.value = [];
}

export function NeuDokumentTab() {
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!vokabular.value) loadVokabular();
  }, []);

  const choices = vokabular.value?.choices ?? {};
  const sorten = vokabular.value?.sorten ?? [];

  async function onFileSelect(f: File) {
    resetForm();
    file.value = f;
    saveSuccess.value = null;
    detecting.value = true;
    detectError.value = null;
    try {
      const suggestion = await detectMetadata(f);
      // Pre-fill form — but NEVER vertraulichkeit
      if (suggestion.titel) titel.value = suggestion.titel;
      if (suggestion.sorte) sorte.value = suggestion.sorte;
      if (suggestion.doc_type) docType.value = suggestion.doc_type;
      if (suggestion.bereich.length) bereich.value = suggestion.bereich;
      if (suggestion.herkunft) herkunft.value = suggestion.herkunft;
      if (suggestion.quelltyp) quelltyp.value = suggestion.quelltyp;
      // vertraulichkeit intentionally NOT set
      if (suggestion.status) status.value = suggestion.status;
      if (suggestion.jahr != null) jahr.value = String(suggestion.jahr);
      if (suggestion.grad) grad.value = suggestion.grad;
      if (suggestion.autor_vorschlag) autor.value = [suggestion.autor_vorschlag];
      if (suggestion.ansprechperson_vorschlag.length)
        ansprechperson.value = suggestion.ansprechperson_vorschlag;
    } catch (err) {
      detectError.value = err instanceof Error ? err.message : String(err);
    } finally {
      detecting.value = false;
    }
  }

  async function onSave() {
    saveError.value = null;
    saveSuccess.value = null;
    if (!file.value) { saveError.value = "Keine Datei ausgewaehlt"; return; }
    if (!sorte.value) { saveError.value = "Sorte ist Pflicht"; return; }
    if (!vertraulichkeit.value) { saveError.value = "Vertraulichkeit ist Pflicht (bewusste Auswahl)"; return; }

    const meta: DokumentMetadata = {
      sorte: sorte.value,
      titel: titel.value || file.value.name,
      doc_type: docType.value,
      bereich: bereich.value,
      herkunft: herkunft.value,
      quelltyp: quelltyp.value,
      vertraulichkeit: vertraulichkeit.value,
      status: status.value,
      jahr: jahr.value ? parseInt(jahr.value, 10) : null,
      grad: grad.value || null,
      thema: thema.value,
      anlage: anlage.value,
      projekt: projekt.value,
      ansprechperson: ansprechperson.value,
      autor: autor.value,
    };

    saving.value = true;
    try {
      const result = await uploadDokument(file.value, meta);
      saveSuccess.value = `Gespeichert: ${result.datei}`;
      resetForm();
      if (fileRef.current) fileRef.current.value = "";
      // Refresh bestand in background
      loadBestand();
    } catch (err) {
      saveError.value = err instanceof Error ? err.message : String(err);
    } finally {
      saving.value = false;
    }
  }

  async function onCreateVok() {
    vokError.value = null;
    if (!vokFacet.value || !vokSlug.value || !vokLabel.value) {
      vokError.value = "Alle Felder ausfuellen";
      return;
    }
    vokSaving.value = true;
    try {
      await createVokabularEntry(vokFacet.value, vokSlug.value, vokLabel.value);
      // Refresh vokabular
      await loadVokabular();
      showVokDialog.value = false;
      vokSlug.value = "";
      vokLabel.value = "";
    } catch (err) {
      vokError.value = err instanceof Error ? err.message : String(err);
    } finally {
      vokSaving.value = false;
    }
  }

  return (
    <div class="p-6 h-full overflow-auto jv-scroll">
      <div class="max-w-[720px] mx-auto">
        <h2 class="text-[15px] font-bold text-text-primary mb-5">
          Neues Dokument hinzufuegen
        </h2>

        {/* Success banner */}
        {saveSuccess.value && (
          <div class="mb-4 p-3 rounded-lg text-[13px] font-medium"
            style={{ background: "rgba(47,158,68,0.08)", border: "1px solid rgba(47,158,68,0.28)", color: "#2f9e44" }}>
            {saveSuccess.value}
            <button class="ml-3 underline cursor-pointer bg-transparent border-none text-[13px]"
              style={{ color: "#2f9e44" }}
              onClick={() => { activeTab.value = "bestand"; saveSuccess.value = null; }}>
              Zum Bestand
            </button>
          </div>
        )}

        {/* File Upload */}
        <div class="mb-5">
          <label class="block text-[12px] font-semibold text-text-secondary mb-[6px]">
            Datei (PDF, DOCX, PPTX, XLSX, MD, TXT)
          </label>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED}
            class="block w-full text-[13px] text-text-body file:mr-3 file:py-[7px] file:px-[14px] file:rounded-lg file:border-none file:text-[12px] file:font-semibold file:bg-panel-3 file:text-text-secondary file:cursor-pointer"
            onChange={(e) => {
              const f = (e.target as HTMLInputElement).files?.[0];
              if (f) onFileSelect(f);
            }}
          />
        </div>

        {/* Detecting spinner */}
        {detecting.value && (
          <div class="mb-4 p-3 rounded-lg bg-panel-2 text-[13px] text-text-muted">
            Metadaten werden erkannt...
          </div>
        )}

        {/* Detect error */}
        {detectError.value && (
          <div class="mb-4 p-3 rounded-lg text-[13px]"
            style={{ background: "rgba(240,96,58,0.08)", border: "1px solid rgba(240,96,58,0.28)", color: "#c0392b" }}>
            Detect-Fehler: {detectError.value}
          </div>
        )}

        {/* Form (visible once file selected) */}
        {file.value && !detecting.value && (
          <div class="flex flex-col gap-4">
            {/* Titel */}
            <Field label="Titel" required>
              <input type="text" value={titel.value}
                onInput={(e) => (titel.value = (e.target as HTMLInputElement).value)}
                class="jv-input" placeholder="Dokumenttitel" />
            </Field>

            {/* Row: Sorte + DocType */}
            <div class="grid grid-cols-2 gap-4">
              <Field label="Sorte (Zielverzeichnis)" required>
                <select value={sorte.value}
                  onChange={(e) => (sorte.value = (e.target as HTMLSelectElement).value)}
                  class="jv-input">
                  <option value="">-- waehlen --</option>
                  {sorten.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </Field>
              <Field label="Dokumenttyp">
                <SelectFromChoices facet="doc_type" value={docType.value}
                  onChange={(v) => (docType.value = v)} choices={choices} />
              </Field>
            </div>

            {/* Row: Bereich + Herkunft */}
            <div class="grid grid-cols-2 gap-4">
              <Field label="Bereich">
                <MultiSelectFromChoices facet="bereich" value={bereich.value}
                  onChange={(v) => (bereich.value = v)} choices={choices} />
              </Field>
              <Field label="Herkunft">
                <SelectFromChoices facet="herkunft" value={herkunft.value}
                  onChange={(v) => (herkunft.value = v)} choices={choices} />
              </Field>
            </div>

            {/* Row: Vertraulichkeit + Quelltyp */}
            <div class="grid grid-cols-2 gap-4">
              <Field label="Vertraulichkeit" required>
                <select value={vertraulichkeit.value}
                  onChange={(e) => (vertraulichkeit.value = (e.target as HTMLSelectElement).value)}
                  class="jv-input"
                  style={!vertraulichkeit.value ? { borderColor: "rgba(240,96,58,0.5)" } : {}}>
                  <option value="">-- bewusst waehlen --</option>
                  {Object.entries(choices["vertraulichkeit"] ?? {}).map(([slug, label]) => (
                    <option key={slug} value={slug}>{label}</option>
                  ))}
                </select>
              </Field>
              <Field label="Quelltyp">
                <SelectFromChoices facet="quelltyp" value={quelltyp.value}
                  onChange={(v) => (quelltyp.value = v)} choices={choices} />
              </Field>
            </div>

            {/* Row: Status + Jahr + Grad */}
            <div class="grid grid-cols-3 gap-4">
              <Field label="Status">
                <SelectFromChoices facet="status" value={status.value}
                  onChange={(v) => (status.value = v)} choices={choices} />
              </Field>
              <Field label="Jahr">
                <input type="number" value={jahr.value}
                  onInput={(e) => (jahr.value = (e.target as HTMLInputElement).value)}
                  class="jv-input" placeholder="z.B. 2024" />
              </Field>
              <Field label="Grad">
                <SelectFromChoices facet="grad" value={grad.value}
                  onChange={(v) => (grad.value = v)} choices={choices} allowEmpty />
              </Field>
            </div>

            {/* Expandable: Thema, Anlage, Projekt, Ansprechperson, Autor */}
            <details class="mt-1">
              <summary class="text-[12px] font-semibold text-text-secondary cursor-pointer select-none">
                Weitere Facetten (Thema, Anlage, Projekt, Autor, Ansprechperson)
              </summary>
              <div class="flex flex-col gap-4 mt-3">
                <Field label="Thema">
                  <MultiSelectFromChoices facet="thema" value={thema.value}
                    onChange={(v) => (thema.value = v)} choices={choices} />
                </Field>
                <Field label="Anlage">
                  <MultiSelectFromChoices facet="anlage" value={anlage.value}
                    onChange={(v) => (anlage.value = v)} choices={choices} />
                </Field>
                <Field label="Projekt">
                  <MultiSelectFromChoices facet="projekt" value={projekt.value}
                    onChange={(v) => (projekt.value = v)} choices={choices} />
                </Field>
                <Field label="Ansprechperson">
                  <MultiSelectFromChoices facet="ansprechperson" value={ansprechperson.value}
                    onChange={(v) => (ansprechperson.value = v)} choices={choices} />
                </Field>
                <Field label="Autor">
                  <MultiSelectFromChoices facet="autor" value={autor.value}
                    onChange={(v) => (autor.value = v)} choices={choices} />
                </Field>
              </div>
            </details>

            {/* New Vocabulary Entry */}
            <div class="mt-1">
              <button
                class="text-[12px] text-text-muted underline cursor-pointer bg-transparent border-none p-0"
                onClick={() => { showVokDialog.value = !showVokDialog.value; vokError.value = null; }}>
                + Neuen Vokabular-Eintrag anlegen
              </button>
              {showVokDialog.value && (
                <div class="mt-2 p-3 rounded-lg border border-border bg-panel-1">
                  <div class="grid grid-cols-3 gap-2 mb-2">
                    <select value={vokFacet.value}
                      onChange={(e) => (vokFacet.value = (e.target as HTMLSelectElement).value)}
                      class="jv-input text-[12px]">
                      <option value="">Facette</option>
                      {["thema", "anlage", "projekt", "ansprechperson", "autor"].map((f) => (
                        <option key={f} value={f}>{f}</option>
                      ))}
                    </select>
                    <input type="text" placeholder="Slug (snake_case)" value={vokSlug.value}
                      onInput={(e) => (vokSlug.value = (e.target as HTMLInputElement).value)}
                      class="jv-input text-[12px]" />
                    <input type="text" placeholder="Anzeigename" value={vokLabel.value}
                      onInput={(e) => (vokLabel.value = (e.target as HTMLInputElement).value)}
                      class="jv-input text-[12px]" />
                  </div>
                  {vokError.value && (
                    <div class="text-[11px] mb-2" style={{ color: "#c0392b" }}>{vokError.value}</div>
                  )}
                  <button onClick={onCreateVok} disabled={vokSaving.value}
                    class="py-[6px] px-[12px] rounded-md text-[12px] font-semibold text-white border-none cursor-pointer"
                    style={{ background: vokSaving.value ? "#ccc" : "#E2001A" }}>
                    {vokSaving.value ? "Speichern..." : "Anlegen"}
                  </button>
                </div>
              )}
            </div>

            {/* Save Error */}
            {saveError.value && (
              <div class="p-3 rounded-lg text-[13px]"
                style={{ background: "rgba(240,96,58,0.08)", border: "1px solid rgba(240,96,58,0.28)", color: "#c0392b" }}>
                {saveError.value}
              </div>
            )}

            {/* Save Button */}
            <button onClick={onSave} disabled={saving.value}
              class="w-full py-[11px] rounded-lg text-[14px] font-semibold text-white border-none cursor-pointer mt-2"
              style={{ background: saving.value ? "#ccc" : "#E2001A" }}>
              {saving.value ? "Speichern..." : "Dokument speichern"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Helpers ──

function Field({ label, required, children }: {
  label: string;
  required?: boolean;
  children: preact.ComponentChildren;
}) {
  return (
    <div>
      <label class="block text-[12px] font-semibold text-text-secondary mb-[6px]">
        {label}{required && <span style={{ color: "#E2001A" }}> *</span>}
      </label>
      {children}
    </div>
  );
}

function SelectFromChoices({ facet, value, onChange, choices, allowEmpty }: {
  facet: string;
  value: string;
  onChange: (v: string) => void;
  choices: Record<string, Record<string, string>>;
  allowEmpty?: boolean;
}) {
  const opts = choices[facet] ?? {};
  return (
    <select value={value}
      onChange={(e) => onChange((e.target as HTMLSelectElement).value)}
      class="jv-input">
      {allowEmpty && <option value="">--</option>}
      {Object.entries(opts).map(([slug, label]) => (
        <option key={slug} value={slug}>{label}</option>
      ))}
    </select>
  );
}

function MultiSelectFromChoices({ facet, value, onChange, choices }: {
  facet: string;
  value: string[];
  onChange: (v: string[]) => void;
  choices: Record<string, Record<string, string>>;
}) {
  const opts = choices[facet] ?? {};
  const toggle = (slug: string) => {
    if (value.includes(slug)) onChange(value.filter((v) => v !== slug));
    else onChange([...value, slug]);
  };
  if (Object.keys(opts).length === 0) {
    return <div class="text-[11px] text-text-muted italic">Keine Eintraege vorhanden</div>;
  }
  return (
    <div class="flex flex-wrap gap-[6px]">
      {Object.entries(opts).map(([slug, label]) => {
        const active = value.includes(slug);
        return (
          <button key={slug} type="button"
            onClick={() => toggle(slug)}
            class="py-[4px] px-[10px] rounded-full text-[11px] font-medium border cursor-pointer transition-colors"
            style={{
              background: active ? "rgba(226,0,26,0.08)" : "transparent",
              borderColor: active ? "rgba(226,0,26,0.3)" : "rgba(0,0,0,0.1)",
              color: active ? "#E2001A" : "#555",
            }}>
            {label}
          </button>
        );
      })}
    </div>
  );
}
