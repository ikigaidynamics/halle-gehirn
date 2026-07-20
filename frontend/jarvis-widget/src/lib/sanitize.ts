/** Strip inline academic citations like [12, p. 8] from text. */

const INLINE_CITATION_RE =
  /\s*\[(?:vgl\.?\s*)?\d+(?:[,\s\-\u2013]+\d+)*(?:[,;]\s*(?:pp?\.?|S\.?|Kap\.?)\s*\d+(?:\s*[-\u2013]\s*\d+)?)?\]/gi;

export function stripInlineCitations(text: string): string {
  return text.replace(INLINE_CITATION_RE, "");
}
