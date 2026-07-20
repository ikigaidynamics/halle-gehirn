/**
 * Lightweight Markdown → HTML converter for assistant messages.
 *
 * Handles: bold, italic, unordered/ordered lists, line breaks,
 * headings (h3–h6), and trailing bare citation numbers.
 * Does NOT handle images, links, code blocks, or tables — those
 * are not expected in LLM chat output.
 */

/** Strip "Quellen: …" footer the LLM sometimes appends. */
const QUELLEN_FOOTER_RE =
  /\n*Quellen:\s*\d[\s\S]*$/;

/** Bare trailing citation numbers like " 1." or " 3." at end of a sentence. */
const BARE_CITE_RE = /\s+\d{1,2}\.(?=\s|$)/g;

/** Escape HTML entities. */
function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function markdownToHtml(raw: string): string {
  // Remove "Quellen:" footer (we show source pills instead)
  let text = raw.replace(QUELLEN_FOOTER_RE, "");

  // Remove bare trailing citation numbers
  text = text.replace(BARE_CITE_RE, "");

  // Split into lines for block-level processing
  const lines = text.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Unordered list: - item or * item
    if (/^\s*[-*]\s+/.test(line)) {
      out.push("<ul class='jv-md-list'>");
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*[-*]\s+/, "");
        out.push(`<li>${inlineFormat(item)}</li>`);
        i++;
      }
      out.push("</ul>");
      continue;
    }

    // Ordered list: 1. item
    if (/^\s*\d+\.\s+/.test(line)) {
      out.push("<ol class='jv-md-list'>");
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const item = lines[i].replace(/^\s*\d+\.\s+/, "");
        out.push(`<li>${inlineFormat(item)}</li>`);
        i++;
      }
      out.push("</ol>");
      continue;
    }

    // Headings: ### Text
    const headingMatch = line.match(/^#{1,6}\s+(.+)$/);
    if (headingMatch) {
      out.push(
        `<div class='jv-md-heading'>${inlineFormat(headingMatch[1])}</div>`,
      );
      i++;
      continue;
    }

    // Empty line → spacing
    if (line.trim() === "") {
      out.push("<br/>");
      i++;
      continue;
    }

    // Normal paragraph
    out.push(`<span>${inlineFormat(line)}</span><br/>`);
    i++;
  }

  // Clean up trailing <br/> tags
  let result = out.join("");
  result = result.replace(/(<br\/>)+$/, "");
  // Collapse triple+ <br/> into double
  result = result.replace(/(<br\/>){3,}/g, "<br/><br/>");

  return result;
}

/** Convert inline markdown (bold, italic) to HTML. */
function inlineFormat(text: string): string {
  let s = esc(text);
  // Bold: **text** or __text__
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  // Italic: *text* or _text_ (single, not inside words)
  s = s.replace(/(?<!\w)\*([^*]+)\*(?!\w)/g, "<em>$1</em>");
  s = s.replace(/(?<!\w)_([^_]+)_(?!\w)/g, "<em>$1</em>");
  // Inline code: `text`
  s = s.replace(
    /`([^`]+)`/g,
    "<code class='jv-md-code'>$1</code>",
  );
  return s;
}
