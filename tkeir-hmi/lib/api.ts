import type { QueryRequest, QueryResponse } from "@/lib/types";
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
