/**
 * Prepare corpus chunk / document text for readable markdown rendering.
 * Retrieval often collapses newlines; restore common markdown structure.
 */

const INDEX_PREFIX_RE =
  /^(?:Active entities:\s*[^.]*\.\s*)?(?:Topic:\s*)?/i;

export function prepareMarkdownForDisplay(raw: string): string {
  let text = (raw || "").replace(/\r\n/g, "\n").replace(/\\n/g, "\n");
  text = text.replace(INDEX_PREFIX_RE, "").trim();
  if (!text) {
    return "";
  }

  const newlineCount = (text.match(/\n/g) || []).length;
  if (newlineCount >= 2) {
    return text;
  }

  // Collapsed ingest markdown, e.g.
  // "# Title body ## Information - **source:** osint - **doc_id:** C2-…"
  // Re-break headings and "- **key:**" attribute bullets only (not title dashes).
  text = text
    .replace(/\s+(#{1,6}\s+)/g, "\n\n$1")
    .replace(/\s+(-\s+\*\*[^*]+?:\*\*)/g, "\n$1");

  return text.trim();
}
