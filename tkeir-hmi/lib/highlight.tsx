import type { ReactNode } from "react";

export interface HighlightLabel {
  label: string;
  kind: "entity" | "keyword";
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function buildHighlightLabels(
  entities: string[],
  keywords: string[],
): HighlightLabel[] {
  const seen = new Set<string>();
  const labels: HighlightLabel[] = [];

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

export function highlightText(
  text: string,
  entities: string[],
  keywords: string[],
): ReactNode[] {
  const labels = buildHighlightLabels(entities, keywords);
  if (!text || labels.length === 0) {
    return [text];
  }

  const pattern = new RegExp(
    `(${labels.map((item) => escapeRegExp(item.label)).join("|")})`,
    "gi",
  );

  const parts = text.split(pattern);
  const lookup = new Map(
    labels.map((item) => [item.label.toLowerCase(), item.kind]),
  );

  return parts.map((part, index) => {
    const kind = lookup.get(part.toLowerCase());
    if (!kind) {
      return part;
    }
    const className =
      kind === "entity"
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
