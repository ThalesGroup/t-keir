import {
  formatDocumentName,
  groupChunksByDocument,
  groupEntitiesByType,
  sortChunksByRelevance,
  type FusedOntology,
  type QueryResponse,
} from "@/lib/types";
import { MIN_KEYWORD_LENGTH } from "@/lib/constants";

export function extractHighlightEntities(ontology: FusedOntology): string[] {
  return [...ontology.entities]
    .sort(
      (a, b) =>
        b.chunk_ids.length - a.chunk_ids.length ||
        a.label.localeCompare(b.label),
    )
    .slice(0, 20)
    .map((entity) => entity.label);
}

export function extractHighlightKeywords(
  ontology: FusedOntology,
  minKeywordLength = MIN_KEYWORD_LENGTH,
): string[] {
  return [...ontology.keywords]
    .filter((keyword) => keyword.label.trim().length >= minKeywordLength)
    .sort(
      (a, b) =>
        b.chunk_ids.length - a.chunk_ids.length ||
        a.label.localeCompare(b.label),
    )
    .slice(0, 15)
    .map((keyword) => keyword.label);
}

function ontologySection(
  ontology: FusedOntology,
  minKeywordLength = MIN_KEYWORD_LENGTH,
): string {
  const grouped = groupEntitiesByType(ontology.entities);
  const lines = ["## Key Entities", ""];

  if (grouped.size === 0) {
    lines.push("- No named entities linked to retrieved chunks.");
  } else {
    for (const [type, entities] of grouped) {
      const labels = [...new Set(entities.map((entity) => entity.label))].sort(
        (a, b) => a.localeCompare(b),
      );
      lines.push(`- **${type}:** ${labels.join(", ")}`);
    }
  }

  lines.push("", "## Key Keywords", "");
  const keywordLabels = [
    ...new Set(
      ontology.keywords
        .map((keyword) => keyword.label)
        .filter((label) => label.trim().length >= minKeywordLength),
    ),
  ].sort((a, b) => a.localeCompare(b));
  if (keywordLabels.length === 0) {
    lines.push("- No keywords linked to retrieved chunks.");
  } else {
    lines.push(`- ${keywordLabels.join(", ")}`);
  }

  return lines.join("\n");
}

function sourcesSection(chunks: QueryResponse["chunks"]): string {
  const lines = ["## Retrieved Sources", ""];
  if (chunks.length === 0) {
    lines.push("No chunks retrieved.");
    return lines.join("\n");
  }

  for (const group of groupChunksByDocument(chunks)) {
    lines.push(`### Document: \`${group.displayName}\``);
    lines.push("");
    lines.push(`- Source URI: \`${group.parentDocId}\``);
    lines.push("");

    for (const chunk of group.chunks) {
      const relevance =
        chunk.relevance !== null
          ? `${(chunk.relevance * 100).toFixed(1)}%`
          : "n/a";
      const excerpt = chunk.text_raw.replace(/\s+/g, " ").trim();
      const trimmed =
        excerpt.length > 1200 ? `${excerpt.slice(0, 1200).trim()}…` : excerpt;

      lines.push(
        `#### Chunk \`${chunk.chunk_id}\` (relevance: ${relevance})`,
      );
      lines.push("");
      lines.push(`> ${trimmed}`);
      lines.push("");
    }
  }

  return lines.join("\n");
}

function detailedAnalysisSection(chunks: QueryResponse["chunks"]): string {
  const lines = [
    "## Detailed Analysis",
    "",
    "Synthesis built from the retrieved chunks most relevant to the query.",
    "",
  ];

  const topChunks = sortChunksByRelevance(chunks).slice(0, 5);

  for (const chunk of topChunks) {
    const relevance =
      chunk.relevance !== null
        ? `${(chunk.relevance * 100).toFixed(1)}%`
        : "n/a";
    const excerpt = chunk.text_raw.replace(/\s+/g, " ").trim();
    const trimmed =
      excerpt.length > 600 ? `${excerpt.slice(0, 600).trim()}…` : excerpt;

    lines.push(`- **[${formatDocumentName(chunk.parent_doc_id)}]** `);
    lines.push(`  Chunk \`${chunk.chunk_id}\` (${relevance} relevance)`);
    lines.push(`  ${trimmed}`);
    lines.push("");
  }

  return lines.join("\n");
}

export function buildClientReportMarkdown(
  response: QueryResponse,
  query: string,
  language: string,
): string {
  const stamp = new Date().toISOString().replace("T", " ").slice(0, 16);

  return [
    "# T-KEIR RAG Report",
    "",
    `- **Generated:** ${stamp} UTC`,
    `- **Language:** ${language}`,
    `- **Vespa hits:** ${response.vespa_hits}`,
    "",
    "## Question",
    "",
    query.trim(),
    "",
    "## Short Answer",
    "",
    response.answer.trim(),
    "",
    detailedAnalysisSection(response.chunks),
    ontologySection(response.ontology),
    "",
    sourcesSection(response.chunks),
    "",
  ].join("\n");
}

export function enrichQueryResponse(
  raw: QueryResponse,
  query: string,
  language: string,
): QueryResponse & {
  report_markdown: string;
  highlight_entities: string[];
  highlight_keywords: string[];
  highlight_query_terms: string[];
} {
  const highlightEntities =
    raw.highlight_entities && raw.highlight_entities.length > 0
      ? raw.highlight_entities
      : extractHighlightEntities(raw.ontology);
  const highlightKeywords =
    raw.highlight_keywords && raw.highlight_keywords.length > 0
      ? raw.highlight_keywords
      : extractHighlightKeywords(raw.ontology);
  const highlightQueryTerms = raw.highlight_query_terms ?? [];
  const reportMarkdown =
    raw.report_markdown?.trim() ||
    buildClientReportMarkdown(raw, query, language);

  return {
    ...raw,
    highlight_entities: highlightEntities,
    highlight_keywords: highlightKeywords,
    highlight_query_terms: highlightQueryTerms,
    report_markdown: reportMarkdown,
  };
}
