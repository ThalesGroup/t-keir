import { auth } from "@/auth";
import { NextRequest, NextResponse } from "next/server";

const PROXY_TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS ?? "300000");

export async function proxyUpstream(
  request: NextRequest,
  pathSegments: string[] | undefined,
  baseUrl: string,
  serviceLabel: string,
): Promise<NextResponse> {
  const path = pathSegments?.join("/") ?? "";
  const target = `${baseUrl.replace(/\/$/, "")}/${path}${request.nextUrl.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  const accept = request.headers.get("accept");
  if (accept) {
    headers.set("accept", accept);
  }

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
    return new NextResponse(body, {
      status: upstream.status,
      headers: responseHeaders,
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Upstream request failed";
    return NextResponse.json(
      {
        detail: `${serviceLabel} proxy error (${message}). Is ${baseUrl} reachable?`,
      },
      { status: 502 },
    );
  }
}
