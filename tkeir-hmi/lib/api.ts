import type {
  OntologyReasonerRequest,
  OntologyReasonerResponse,
  QueryRequest,
  QueryResponse,
  SearchResponse,
} from "@/lib/types";
import { enrichQueryResponse } from "@/lib/report";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "/api";

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
    response = await fetch(`${API_BASE}${path}`, {
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

export async function queryOntologyReasoner(
  request: OntologyReasonerRequest,
): Promise<OntologyReasonerResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/rag/ontology/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
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
