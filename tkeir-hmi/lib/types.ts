/** T-KEIR RAG API types — mirrors `thot.tools.search.app` Pydantic models. */

export type Language = "en" | "fr";

export interface QueryRequest {
  query: string;
  language: Language;
  hits: number;
  /** Override rag.yaml prompt.passages.count */
  max_passages?: number;
  /** Override rag.yaml prompt.passages.max_chars */
  max_chars_per_passage?: number;
  /** Override rag.yaml prompt.passages.context_sentences */
  focus_context_sentences?: number;
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
  json_ld: string;
  /** RDF triple count in the fused graph */
  triple_count?: number;
  /** Number of unique Vespa parent ontology payloads merged */
  source_count?: number;
  /** Parent document ids that contributed ontology */
  document_ids?: string[];
}

export type OntologyReasonerOperation =
  | "consistency"
  | "subclasses"
  | "superclasses"
  | "instances"
  | "types"
  | "sparql"
  | "infer";

export type OntologyReasonerEngine =
  | "HermiT"
  | "Pellet"
  | "ELK"
  | "JFact"
  | "Openllet"
  | "Structural"
  | "rdflib";

export interface OntologyReasonerRequest {
  json_ld: string;
  operation: OntologyReasonerOperation | string;
  class_iri?: string;
  individual_iri?: string;
  sparql?: string;
  reasoner?: OntologyReasonerEngine | string;
  direct?: boolean;
  limit?: number;
  prefer_owlapy?: boolean;
}

export interface OntologyReasonerResponse {
  operation: string;
  backend: string;
  reasoner?: string;
  results: Record<string, string>[];
  count: number;
  consistent?: boolean | null;
  triple_count: number;
  owlapy_available: boolean;
  note?: string | null;
  /** JSON-LD graph of the reasoner answer (for display / graph view) */
  json_ld?: string | null;
}

export interface QueryResponse {
  answer: string;
  report_markdown?: string;
  input_prompt?: string;
  vespa_query?: string;
  highlight_entities?: string[];
  highlight_keywords?: string[];
  highlight_query_terms?: string[];
  used_chunk_evidence?: boolean;
  answer_unavailable?: boolean;
  chunks: RetrievedChunk[];
  ontology: FusedOntology;
  vespa_hits: number;
}

export interface DocumentGroup {
  parentDocId: string;
  displayName: string;
  chunks: RetrievedChunk[];
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
