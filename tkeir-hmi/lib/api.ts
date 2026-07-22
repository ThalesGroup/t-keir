import type {
  OntologyReasonerRequest,
  OntologyReasonerResponse,
  QueryRequest,
  QueryResponse,
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

export async function queryRag(request: QueryRequest): Promise<RagQueryResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/rag/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Network request failed";
    throw new RagApiError(
      `Cannot reach RAG API (${message}). Start with: make rag`,
    );
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

  const raw = (await response.json()) as QueryResponse;
  return {
    response: enrichQueryResponse(raw, request.query, request.language),
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
