import { prepareMarkdownForDisplay } from "@/lib/markdown";
import type { SearchChunkHit, SearchDocumentHit } from "@/lib/types";

const HASH_RE = /^[a-f0-9]{16,}$/i;
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const RECORD_ID_RE = /^[A-Z]{1,6}-\d{4,}(?:[-_]\d+)?$/i;
const FILE_EXT_RE =
  /\.(?:txt|md|markdown|pdf|xml|json|docx|pptx|xlsx|html|htm|csv|zip)(?:\.md)?$/i;
const SKIP_HEADING_RE =
  /^(information|metadata|active entities|topic|article|talk|contents|references|see also|external links|notes|appendix|history|summary|overview|introduction)$/i;
const PROTOCOL_LABELS = [
  "Active entities",
  "Upcoming entities",
  "Topic",
  "Previous context",
  "Next focus",
  "Continues with",
];
const PROTOCOL_STRIP_RE = new RegExp(
  `(?:${PROTOCOL_LABELS.map((label) => label.replace(/\s+/g, "\\s+")).join("|")}):[^.\\n]*\\.\\s*`,
  "gi",
);
const NOISE_LEAD_RE =
  /^(donate|create account|log in|sign in|from wikipedia|this page was last edited|jump to|\[edit\]|read$|edit$|view history)$/i;
const WIKI_PREAMBLE_RE =
  /.*?From Wikipedia,\s+the free encyclopedia\s*/i;

export interface SearchHitGroup {
  parentDocId: string;
  title: string;
  sourceLabel: string;
  score: number;
  chunks: SearchChunkHit[];
}

export function stripHeadingMarks(value: string): string {
  return (value || "")
    .replace(/^#{1,6}\s+/, "")
    .replace(/\*\*/g, "")
    .replace(/^["'`]+|["'`]+$/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function looksTechnicalId(value: string): boolean {
  const text = stripHeadingMarks(value);
  if (!text) return true;
  if (HASH_RE.test(text) || UUID_RE.test(text)) return true;
  if (RECORD_ID_RE.test(text)) return true;
  if (text.includes("#") && /chunk[-_]/i.test(text)) return true;
  if (/^chunk[-_]?\d/i.test(text)) return true;
  if (text.startsWith("file:") || text.startsWith("ingest:")) return true;
  if (text.includes("/") && !/\s/.test(text)) return true;
  if (FILE_EXT_RE.test(text) && !/\s/.test(text)) return true;
  if (/^[0-9a-f]{8,}$/i.test(text) && !/[aeiou]/i.test(text)) return true;
  return false;
}

function isUsefulHeadline(value: string): boolean {
  const text = stripHeadingMarks(value);
  if (!text || looksTechnicalId(text) || SKIP_HEADING_RE.test(text)) {
    return false;
  }
  const words = text.split(/\s+/).filter(Boolean);
  if (words.length >= 3) return true;
  if (text.length >= 18 && /[a-zA-Z\u00C0-\u024F]/.test(text)) return true;
  return false;
}

/** Core passage: drop Vespa context wrappers and golden-chunk protocol lines. */
export function corePassageText(text: string): string {
  let body = text || "";
  body = body.replace(/\[CONTEXT_AFTER\][\s\S]*$/i, "");
  body = body.replace(/^[\s\S]*?\[CONTEXT_BEFORE\]\s*/i, "");
  body = body.replace(PROTOCOL_STRIP_RE, "");
  for (const label of PROTOCOL_LABELS) {
    body = body.replace(new RegExp(`\\b${label}:\\s*`, "i"), "");
  }
  body = body.replace(WIKI_PREAMBLE_RE, "");
  body = prepareMarkdownForDisplay(body);
  const infoAt = body.search(/^#{1,6}\s+Information\b/im);
  if (infoAt >= 0) {
    body = body.slice(0, infoAt);
  }
  return body.trim();
}

export function headingFromPassage(text: string): string {
  const restored = prepareMarkdownForDisplay(text || "");
  for (const line of restored.split("\n")) {
    const match = line.match(/^#{1,6}\s+(.+)$/);
    if (!match) continue;
    const heading = stripHeadingMarks(match[1]);
    if (!heading || SKIP_HEADING_RE.test(heading)) continue;
    if (looksTechnicalId(heading) || !isUsefulHeadline(heading)) continue;
    return heading;
  }
  return "";
}

function firstSentences(
  text: string,
  maxChars = 110,
  entityLabels: string[] = [],
): string {
  let cleaned = corePassageText(text)
    .replace(/^#{1,6}\s+.+$/gm, "")
    .replace(/^[-*]\s+\*\*[^*]+?:\*\*.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  const focal = entityLabels.find((label) => label.trim().length >= 3);
  if (focal) {
    const idx = cleaned.toLowerCase().indexOf(focal.toLowerCase());
    if (idx > 16) {
      cleaned = cleaned.slice(idx).replace(/^[,.;:\s]+/, "");
    }
  }
  if (!cleaned) return "";
  const parts = cleaned
    .split(/(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter((part) => {
      if (part.length < 24) return false;
      if (NOISE_LEAD_RE.test(part.replace(/[.]+$/, ""))) return false;
      if (SKIP_HEADING_RE.test(part)) return false;
      return true;
    });
  if (parts.length === 0) {
    return truncateLabel(cleaned, maxChars);
  }
  let lead = parts[0].replace(/[.]+$/, "");
  if (lead.length < 48 && parts[1]) {
    lead = `${lead} — ${parts[1].replace(/[.]+$/, "")}`;
  }
  return truncateLabel(lead, maxChars);
}

export function extractTopicPhrase(text: string): string {
  if (/\[CONTEXT_BEFORE\]/i.test(text || "")) {
    return "";
  }
  const core = (text || "").split(/\[CONTEXT_AFTER\]/i)[0] || "";
  const match = core.match(/\bTopic:\s*([^.\n]+)/i);
  if (!match) return "";
  const topic = stripHeadingMarks(match[1]);
  return isUsefulHeadline(topic) ? topic : "";
}

export function explicitChunkTitle(
  chunk: { text_raw: string; title?: string | null; parent_doc_id?: string },
  opts?: {
    documentTitle?: string;
    entityLabels?: string[];
  },
): string {
  const raw = chunk.text_raw || "";
  const fromApi = stripHeadingMarks(chunk.title || "");
  const topic = extractTopicPhrase(raw);
  const heading = headingFromPassage(raw);
  const lead = firstSentences(raw, 110, opts?.entityLabels);
  const entity = (opts?.entityLabels || []).find(
    (label) => label.trim() && !looksTechnicalId(label),
  );
  const documentTitle = stripHeadingMarks(opts?.documentTitle || "");

  const qualify = (headline: string): string => {
    const text = headline.trim();
    if (
      entity &&
      entity.length >= 3 &&
      !text.toLowerCase().includes(entity.toLowerCase())
    ) {
      return truncateLabel(`${entity} — ${text}`, 130);
    }
    return truncateLabel(text, 130);
  };

  if (fromApi && isUsefulHeadline(fromApi)) {
    if (lead && lead.localeCompare(fromApi, undefined, { sensitivity: "accent" }) !== 0) {
      return qualify(`${fromApi} — ${lead}`);
    }
    return qualify(fromApi);
  }
  if (topic) {
    return qualify(topic);
  }
  if (heading && lead && heading.localeCompare(lead, undefined, { sensitivity: "accent" }) !== 0) {
    return qualify(`${heading} — ${lead}`);
  }
  if (heading) {
    return qualify(heading);
  }
  if (lead) {
    return qualify(lead);
  }
  if (documentTitle && isUsefulHeadline(documentTitle)) {
    return qualify(documentTitle);
  }
  if (entity) {
    return truncateLabel(entity, 80);
  }
  return "Passage";
}

export function humanizeSourceName(parentDocId: string): string {
  let value = (parentDocId || "").trim();
  value = value.replace(/^(?:file:\/\/|ingest:\/\/)/i, "");
  value = value.replace(/^user:[^:]+:/i, "");
  const segment = value.split("/").filter(Boolean).pop() || value;
  let name = segment.replace(/(\.md)+$/i, "");
  name = name.replace(FILE_EXT_RE, "");
  name = name.replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
  if (!name || looksTechnicalId(name) || looksTechnicalId(segment)) {
    return "";
  }
  return name;
}

export function formatSourceLabel(parentDocId: string): string {
  let value = (parentDocId || "").trim();
  if (!value) return "";
  value = value.replace(/^(?:file:\/\/)/i, "");
  value = value.replace(/^user:[^:]+:/i, "My files / ");
  value = value.replace(/^ingest:\/\//i, "");
  const parts = value.split("/").filter(Boolean);
  if (parts.length >= 3) {
    return parts.slice(-2).join("/");
  }
  return parts.join("/") || value;
}

export function displayHitTitle(input: {
  title?: string | null;
  text?: string | null;
  parentDocId?: string | null;
  entityLabels?: string[];
}): string {
  return explicitChunkTitle(
    {
      text_raw: input.text || "",
      title: input.title,
      parent_doc_id: input.parentDocId || "",
    },
    { entityLabels: input.entityLabels },
  );
}

export function displayPassageTitle(
  chunk: { text_raw: string; title?: string },
  documentTitle: string,
  indexInDocument: number,
  entityLabels: string[] = [],
): string {
  const title = explicitChunkTitle(chunk, {
    documentTitle,
    entityLabels,
  });
  if (title && title !== "Passage") {
    return title;
  }
  return `Passage ${indexInDocument + 1}`;
}

export function passageSnippet(text: string, max = 180): string {
  const lead = firstSentences(text, max);
  if (lead) return lead;
  let body = corePassageText(text);
  body = body.replace(/^#{1,6}\s+.+$/gm, "");
  body = body
    .replace(/^[-*]\s+\*\*[^*]+?:\*\*.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!body) return "";
  return truncateLabel(body, max);
}

export function matchStrength(score: number, maxScore: number): number {
  if (!(maxScore > 0) || !(score > 0)) return 0;
  return Math.max(0, Math.min(1, score / maxScore));
}

export function groupSearchHits(
  chunks: SearchChunkHit[],
  documents: SearchDocumentHit[] = [],
): SearchHitGroup[] {
  const titleByDoc = new Map(
    documents.map((doc) => [doc.document_id, doc.title || ""] as const),
  );
  const grouped = new Map<string, SearchChunkHit[]>();
  for (const chunk of chunks) {
    const key = chunk.parent_doc_id || chunk.chunk_id;
    const list = grouped.get(key) ?? [];
    list.push(chunk);
    grouped.set(key, list);
  }

  const groups: SearchHitGroup[] = [];
  for (const [parentDocId, docChunks] of grouped.entries()) {
    const ordered = [...docChunks].sort((a, b) => b.score - a.score);
    const best = ordered[0];
    const title = explicitChunkTitle(
      {
        text_raw: best?.text_raw || "",
        title: titleByDoc.get(parentDocId) || best?.title,
        parent_doc_id: parentDocId,
      },
    );
    groups.push({
      parentDocId,
      title,
      sourceLabel: formatSourceLabel(parentDocId),
      score: best?.score ?? 0,
      chunks: ordered,
    });
  }
  groups.sort((a, b) => b.score - a.score);
  return groups;
}

function truncateLabel(value: string, max = 120): string {
  const text = value.trim();
  if (text.length <= max) return text;
  return `${text.slice(0, Math.max(0, max - 1)).trimEnd()}…`;
}
