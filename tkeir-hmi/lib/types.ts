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
  /** Merged with datasets/<dataset>/business_ontology.yaml */
  business_ontology?: Record<string, unknown> | Record<string, unknown>[];
  /** Dataset folder under datasets/ (default: osint) */
  business_ontology_dataset?: string;
  /** Server path to ingest dump root (staging/ + source_refs.json) */
  analyzed_documents_path?: string;
  /** Extra JSON-LD merged into fused response ontology */
  ontology_json_ld?: string;
  /** Dual-hybrid: auto | global | user | both */
  search_mode?: "auto" | "global" | "user" | "both" | string;
  /** Restrict retrieval to these workspace/Vespa source_ref values */
  source_refs?: string[];
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
  /** Text-importance weight (chunk coverage + summed text hits). */
  weight?: number;
  mention_count?: number;
  text_hits?: number;
}

export interface SemanticKeyword {
  label: string;
  chunk_ids: string[];
  /** Text-importance weight (chunk coverage + summed text hits). */
  weight?: number;
  mention_count?: number;
  text_hits?: number;
}

export interface OntologyRelation {
  source: string;
  predicate: string;
  target: string;
  /** Fuse-summed occurrence weight across chunk/parent ontologies. */
  weight: number;
}

export interface ProposedOntologyQuery {
  kind: "sparql" | "expression" | "coherence" | string;
  title: string;
  query: string;
  description?: string;
}

export interface FusedOntology {
  entities: SemanticEntity[];
  keywords: SemanticKeyword[];
  json_ld: string;
  /** Weighted relations summed across fused chunk ontologies */
  relations?: OntologyRelation[];
  /** RDF triple count in the fused graph */
  triple_count?: number;
  /** Number of unique Vespa parent ontology payloads merged */
  source_count?: number;
  /** Parent document ids that contributed ontology */
  document_ids?: string[];
  /** SPARQL / expression / coherence chips for the Reason tab */
  proposed_queries?: ProposedOntologyQuery[];
}

export type OntologyReasonerOperation =
  | "consistency"
  | "subclasses"
  | "superclasses"
  | "instances"
  | "types"
  | "sparql"
  | "expression"
  | "infer";

/** Single pure-Python reasoner. */
export type OntologyReasonerEngine = "python";

export interface OntologyReasonerRequest {
  json_ld: string;
  operation: OntologyReasonerOperation | string;
  class_iri?: string;
  individual_iri?: string;
  sparql?: string;
  expression?: string;
  reasoner?: OntologyReasonerEngine | string;
  direct?: boolean;
  limit?: number;
  business_ontology?: Record<string, unknown> | Record<string, unknown>[];
  business_ontology_dataset?: string;
}

export interface OntologyReasonerResponse {
  operation: string;
  backend: string;
  reasoner?: string;
  results: Record<string, string>[];
  count: number;
  consistent?: boolean | null;
  triple_count: number;
  note?: string | null;
  /** JSON-LD graph of the reasoner answer (for display / graph view) */
  json_ld?: string | null;
  expression?: string | null;
  sparql?: string | null;
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

/** Retrieval-only `/search` (no LLM answer). */
export interface SearchChunkHit {
  chunk_id: string;
  text_raw: string;
  parent_doc_id: string;
  score: number;
  title?: string;
}

export interface SearchDocumentHit {
  document_id: string;
  score: number;
  chunk_ids: string[];
  title?: string;
  hit_count: number;
}

export interface SearchTimings {
  nlp_ms: number;
  vespa_ms?: number;
  vespa_chunk_ms: number;
  vespa_document_ms: number;
  rrf_ms: number;
  rerank_ms: number;
  ontology_ms?: number;
  lexical_ms?: number;
  total_ms?: number;
}

export interface SearchResponse {
  query: string;
  chunks: SearchChunkHit[];
  documents: SearchDocumentHit[];
  vespa_hits: number;
  ranking_profile?: string | null;
  /** Global fused ontology from retrieved chunk/parent documents. */
  ontology?: FusedOntology | null;
  /** Query NLP (+ matched external BO) ontology. */
  query_ontology?: FusedOntology | null;
  /** Union of query_ontology and ontology. */
  merged_ontology?: FusedOntology | null;
  timings?: SearchTimings | null;
}

export type WorkspaceMode =
  | "search"
  | "rag"
  | "reporter"
  | "wiki"
  | "agent"
  | "files"
  | "ingest";

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
