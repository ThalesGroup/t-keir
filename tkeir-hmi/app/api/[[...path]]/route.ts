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
