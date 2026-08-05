import type {
  Language,
  OntologyReasonerRequest,
  OntologyReasonerResponse,
  QueryRequest,
  QueryResponse,
  SearchResponse,
} from "@/lib/types";
import { enrichQueryResponse } from "@/lib/report";
import { apiFetch } from "@/src/auth/useApiClient";
import type { RuntimeConfig } from "@/src/config/runtimeConfig";
import { resolveBusinessOntologyDataset } from "@/lib/business-ontology-datasets";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "/api";

/** Ontology dump + business-ontology dataset fields for /search and /rag/query. */
export function ontologyQueryOptions(
  runtimeConfig: RuntimeConfig | null | undefined,
  datasetOverride?: string | null,
): Pick<
  QueryRequest,
  "analyzed_documents_path" | "business_ontology_dataset"
> {
  return {
    analyzed_documents_path:
      runtimeConfig?.analyzedDocumentsPath?.trim() || "workspace/ingest",
    business_ontology_dataset: resolveBusinessOntologyDataset(
      runtimeConfig?.businessOntologyDataset,
      datasetOverride,
    ),
  };
}

export class RagApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "RagApiError";
  }
}

export interface RagQueryResult {
  response: QueryResponse;
  correlationId: string | null;
}

export interface SearchQueryResult {
  response: SearchResponse;
  correlationId: string | null;
}

async function postJson<T>(
  path: string,
  body: unknown,
  unreachableHint: string,
): Promise<{ data: T; correlationId: string | null }> {
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(`${unreachableHint} (${message})`);
  }

  const correlationId =
    response.headers.get("x-correlation-id") ||
    response.headers.get("X-Correlation-Id");

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // keep default message
    }
    throw new RagApiError(detail, response.status);
  }

  return {
    data: (await response.json()) as T,
    correlationId,
  };
}

/** Retrieval-only hybrid search (no LLM report). */
export async function querySearch(
  request: QueryRequest,
): Promise<SearchQueryResult> {
  const { data, correlationId } = await postJson<SearchResponse>(
    "/search",
    request,
    "Cannot reach search API. Start with: make rag",
  );
  return { response: data, correlationId };
}

export async function queryRag(request: QueryRequest): Promise<RagQueryResult> {
  const { data, correlationId } = await postJson<QueryResponse>(
    "/rag/query",
    request,
    "Cannot reach RAG API. Start with: make rag",
  );
  return {
    response: enrichQueryResponse(data, request.query, request.language),
    correlationId,
  };
}

export type AnalyzedDocumentPayload = {
  source_doc_id?: string;
  source?: string;
  title?: string;
  document_ontology?: {
    json_ld?: string;
    shacl_status?: string;
    [key: string]: unknown;
  };
  golden_chunks?: Array<{
    chunk_id?: string;
    text_raw?: string;
    parent_doc_id?: string;
  }>;
  [key: string]: unknown;
};

/** Load one analyzed ingest document by Vespa/workspace ``source_ref``. */
export async function getAnalyzedDocument(
  sourceRef: string,
  runtimeConfig?: RuntimeConfig | null,
): Promise<AnalyzedDocumentPayload> {
  const analyzedPath =
    runtimeConfig?.analyzedDocumentsPath?.trim() || "workspace/ingest";
  const qs = new URLSearchParams({
    source_ref: sourceRef,
    analyzed_documents_path: analyzedPath,
  });
  let response: Response;
  try {
    response = await apiFetch(
      `${API_BASE}/documents/analyzed?${qs.toString()}`,
      { cache: "no-store" },
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(
      `Cannot reach analyzed-document API (${message}). Start with: make rag`,
    );
  }
  if (!response.ok) {
    let detail = `No analyzed document for ${sourceRef} (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // keep default
    }
    throw new RagApiError(detail, response.status);
  }
  return (await response.json()) as AnalyzedDocumentPayload;
}

export type BusinessOntologyParseResult = {
  business_ontology: Record<string, unknown>;
  concept_count: number;
  filename?: string | null;
};

/** Parse an uploaded ``business_ontology.yaml`` / JSON via the search API. */
export async function parseBusinessOntologyFile(
  file: File,
): Promise<BusinessOntologyParseResult> {
  const form = new FormData();
  form.append("business_ontology", file, file.name);
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}/business-ontology/parse`, {
      method: "POST",
      body: form,
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(
      `Cannot reach business-ontology parse API (${message}). Start with: make rag`,
    );
  }
  if (!response.ok) {
    let detail = `Invalid business ontology file (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // keep default
    }
    throw new RagApiError(detail, response.status);
  }
  return (await response.json()) as BusinessOntologyParseResult;
}

/** Run NLP pipeline on an uploaded document (no Vespa index). */
export async function analyzeDocumentFile(options: {
  file: Blob;
  filename: string;
  language?: Language;
  datatype?: string;
  businessOntologyFile?: Blob;
  businessOntologyFilename?: string;
}): Promise<AnalyzedDocumentPayload> {
  const form = new FormData();
  form.append("file", options.file, options.filename);
  form.append("language", options.language || "en");
  form.append("datatype", options.datatype || "raw");
  if (options.businessOntologyFile) {
    form.append(
      "business_ontology",
      options.businessOntologyFile,
      options.businessOntologyFilename || "business_ontology.json",
    );
  }
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}/documents/analyze`, {
      method: "POST",
      body: form,
      cache: "no-store",
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(
      `Cannot reach document analyze API (${message}). Start with: make rag`,
    );
  }
  if (!response.ok) {
    let detail = `Document analyze failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // keep default
    }
    throw new RagApiError(detail, response.status);
  }
  return (await response.json()) as AnalyzedDocumentPayload;
}

export async function queryOntologyReasoner(
  request: OntologyReasonerRequest,
  runtimeConfig?: RuntimeConfig | null,
): Promise<OntologyReasonerResponse> {
  const { business_ontology_dataset } = ontologyQueryOptions(runtimeConfig);
  const body: OntologyReasonerRequest = {
    reasoner: "python",
    business_ontology_dataset,
    ...request,
  };
  let response: Response;
  try {
    response = await apiFetch(`${API_BASE}/rag/ontology/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(
      `Cannot reach RAG ontology reasoner (${message}). Start with: make rag`,
    );
  }
  if (!response.ok) {
    let detail = `Ontology query failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // keep default
    }
    throw new RagApiError(detail, response.status);
  }
  return (await response.json()) as OntologyReasonerResponse;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** True when tkeir-agent is reachable via the HMI `/api/agent` proxy. */
export async function checkAgentHealth(): Promise<boolean> {
  try {
    const response = await fetch("/api/agent/health", {
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}
