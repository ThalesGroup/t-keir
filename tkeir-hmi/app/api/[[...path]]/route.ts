import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";

const API_URL = (process.env.API_URL ?? "http://localhost:8090").replace(
  /\/$/,
  "",
);

/** RAG + LLM queries can take several minutes; avoid short dev-proxy timeouts. */
const PROXY_TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS ?? "300000");

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[] | undefined,
): Promise<NextResponse> {
  const path = pathSegments?.join("/") ?? "";
  const target = `${API_URL}/${path}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("accept", accept);
  }

  // Propagate W3C trace context and inbound correlation id.
  const traceparent = request.headers.get("traceparent");
  if (traceparent) {
    headers.set("traceparent", traceparent);
  }
  const correlationId = request.headers.get("x-correlation-id");
  if (correlationId) {
    headers.set("x-correlation-id", correlationId);
  }

  // Forward bearer from Auth.js session when present.
  if (process.env.AUTH_ENABLED === "true") {
    const session = await auth();
    if (session?.accessToken) {
      headers.set("authorization", `Bearer ${session.accessToken}`);
    }
  }
  const inboundAuth = request.headers.get("authorization");
  if (inboundAuth && !headers.has("authorization")) {
    headers.set("authorization", inboundAuth);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    signal: AbortSignal.timeout(PROXY_TIMEOUT_MS),
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  try {
    const upstream = await fetch(target, init);
    const body = await upstream.text();
    const responseHeaders = new Headers();
    const upstreamType = upstream.headers.get("content-type");
    if (upstreamType) {
      responseHeaders.set("content-type", upstreamType);
    }
    const upstreamCorrelation =
      upstream.headers.get("x-correlation-id") ||
      upstream.headers.get("X-Correlation-Id");
    if (upstreamCorrelation) {
      responseHeaders.set("x-correlation-id", upstreamCorrelation);
    }
    const upstreamTrace = upstream.headers.get("traceparent");
    if (upstreamTrace) {
      responseHeaders.set("traceparent", upstreamTrace);
    }
    // Expose correlation header to browser JS (fetch).
    responseHeaders.set(
      "access-control-expose-headers",
      "x-correlation-id, traceparent",
    );
    return new NextResponse(body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json(
      {
        detail: `RAG API proxy error (${message}). Is the server running on ${API_URL}?`,
      },
      { status: 502 },
    );
  }
}

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyRequest(request, path);
}
