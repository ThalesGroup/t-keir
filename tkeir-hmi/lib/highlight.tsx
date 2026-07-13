import type { ReactNode } from "react";

export interface HighlightLabel {
  label: string;
  kind: "entity" | "keyword" | "query";
}

const highlightPatternCache = new Map<string, RegExp>();
const highlightLookupCache = new Map<
  string,
  Map<string, HighlightLabel["kind"]>
>();

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildHighlightLabels(
  entities: string[],
  keywords: string[],
  queryTerms: string[] = [],
): HighlightLabel[] {
  const seen = new Set<string>();
  const labels: HighlightLabel[] = [];

  for (const label of queryTerms) {
    const trimmed = label.trim();
    const key = trimmed.toLowerCase();
    if (trimmed && !seen.has(key)) {
      seen.add(key);
      labels.push({ label: trimmed, kind: "query" });
    }
  }

  for (const label of entities) {
    const trimmed = label.trim();
    const key = trimmed.toLowerCase();
    if (trimmed && !seen.has(key)) {
      seen.add(key);
      labels.push({ label: trimmed, kind: "entity" });
    }
  }

  for (const label of keywords) {
    const trimmed = label.trim();
    const key = trimmed.toLowerCase();
    if (trimmed && !seen.has(key)) {
      seen.add(key);
      labels.push({ label: trimmed, kind: "keyword" });
    }
  }

  return labels.sort((a, b) => b.label.length - a.label.length);
}

function highlightCacheKey(
  entities: string[],
  keywords: string[],
  queryTerms: string[],
): string {
  return `${queryTerms.join("\u0001")}\u0002${entities.join("\u0001")}\u0003${keywords.join("\u0001")}`;
}

function getHighlightPattern(
  entities: string[],
  keywords: string[],
  queryTerms: string[],
): { pattern: RegExp | null; lookup: Map<string, HighlightLabel["kind"]> } {
  const labels = buildHighlightLabels(entities, keywords, queryTerms);
  if (labels.length === 0) {
    return { pattern: null, lookup: new Map() };
  }

  const cacheKey = highlightCacheKey(entities, keywords, queryTerms);
  let pattern = highlightPatternCache.get(cacheKey);
  let lookup = highlightLookupCache.get(cacheKey);
  if (!pattern || !lookup) {
    pattern = new RegExp(
      `(${labels.map((item) => escapeRegExp(item.label)).join("|")})`,
      "gi",
    );
    lookup = new Map(
      labels.map((item) => [item.label.toLowerCase(), item.kind]),
    );
    highlightPatternCache.set(cacheKey, pattern);
    highlightLookupCache.set(cacheKey, lookup);
  }

  return { pattern, lookup };
}

export function highlightText(
  text: string,
  entities: string[],
  keywords: string[],
  queryTerms: string[] = [],
): ReactNode[] {
  if (!text) {
    return [text];
  }

  const { pattern, lookup } = getHighlightPattern(
    entities,
    keywords,
    queryTerms,
  );
  if (!pattern) {
    return [text];
  }

  const parts = text.split(pattern);

  return parts.map((part, index) => {
    const kind = lookup.get(part.toLowerCase());
    if (!kind) {
      return part;
    }
    const className =
      kind === "query"
        ? "rounded bg-yellow-300 px-1 py-0.5 font-semibold text-yellow-950 shadow-sm ring-1 ring-yellow-400/80 dark:bg-yellow-300 dark:text-yellow-950"
        : kind === "entity"
          ? "rounded bg-indigo-200/80 px-1 py-0.5 font-medium text-indigo-950 dark:bg-indigo-900/70 dark:text-indigo-100"
          : "rounded bg-emerald-200/80 px-1 py-0.5 font-medium text-emerald-950 dark:bg-emerald-900/70 dark:text-emerald-100";
    return (
      <mark key={`${part}-${index}`} className={className}>
        {part}
      </mark>
    );
  });
}

export function downloadMarkdown(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function reportFilename(query: string): string {
  const slug = query
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48);
  const stamp = new Date().toISOString().slice(0, 10);
  return `tkeir-rag-report-${slug || "query"}-${stamp}.md`;
}
