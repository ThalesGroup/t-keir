/** T-KEIR RAG API types — mirrors `thot.tools.search.app` Pydantic models. */

export type Language = "en" | "fr";

export interface QueryRequest {
  query: string;
  language: Language;
  hits: number;
}

export interface RetrievedChunk {
  chunk_id: string;
  text_raw: string;
  parent_doc_id: string;
  relevance: number | null;
}

export interface SemanticEntity {
  label: string;
  type: string;
  chunk_ids: string[];
}

export interface SemanticKeyword {
  label: string;
  chunk_ids: string[];
}

export interface FusedOntology {
  entities: SemanticEntity[];
  keywords: SemanticKeyword[];
}

export interface QueryResponse {
  answer: string;
  report_markdown?: string;
  highlight_entities?: string[];
  highlight_keywords?: string[];
  chunks: RetrievedChunk[];
  ontology: FusedOntology;
  vespa_hits: number;
}

export interface DocumentGroup {
  parentDocId: string;
  displayName: string;
  chunks: RetrievedChunk[];
}

export const UNAVAILABLE_ANSWERS = new Set([
  "L'information n'est pas disponible.",
  "The information is not available.",
]);

export function isUnavailableAnswer(answer: string): boolean {
  return UNAVAILABLE_ANSWERS.has(answer.trim());
}

export function formatDocumentName(parentDocId: string): string {
  const withoutScheme = parentDocId.replace(/^file:\/\//, "");
  const segments = withoutScheme.split("/");
  return segments[segments.length - 1] || parentDocId;
}

export function chunkRelevanceScore(chunk: RetrievedChunk): number {
  return chunk.relevance ?? 0;
}

export function sortChunksByRelevance(
  chunks: RetrievedChunk[],
): RetrievedChunk[] {
  return [...chunks].sort(
    (a, b) => chunkRelevanceScore(b) - chunkRelevanceScore(a),
  );
}

function groupTopRelevance(chunks: RetrievedChunk[]): number {
  return chunks.reduce(
    (max, chunk) => Math.max(max, chunkRelevanceScore(chunk)),
    0,
  );
}

export function groupChunksByDocument(
  chunks: RetrievedChunk[],
): DocumentGroup[] {
  const groups = new Map<string, RetrievedChunk[]>();

  for (const chunk of chunks) {
    const existing = groups.get(chunk.parent_doc_id) ?? [];
    existing.push(chunk);
    groups.set(chunk.parent_doc_id, existing);
  }

  return Array.from(groups.entries())
    .map(([parentDocId, docChunks]) => ({
      parentDocId,
      displayName: formatDocumentName(parentDocId),
      chunks: sortChunksByRelevance(docChunks),
    }))
    .sort((a, b) => groupTopRelevance(b.chunks) - groupTopRelevance(a.chunks));
}

export function groupEntitiesByType(
  entities: SemanticEntity[],
): Map<string, SemanticEntity[]> {
  const grouped = new Map<string, SemanticEntity[]>();

  for (const entity of entities) {
    const bucket = grouped.get(entity.type) ?? [];
    bucket.push(entity);
    grouped.set(entity.type, bucket);
  }

  return new Map(
    [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b)),
  );
}

export function chunkMatchesFilter(
  chunkId: string,
  activeChunkIds: Set<string> | null,
): boolean {
  if (activeChunkIds === null || activeChunkIds.size === 0) {
    return true;
  }
  return activeChunkIds.has(chunkId);
}
