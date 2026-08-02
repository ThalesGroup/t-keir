import { NextRequest } from "next/server";

import { proxyUpstream } from "@/lib/admin-proxy";

const INGEST_URL = process.env.INGEST_URL ?? "http://localhost:8091";

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, INGEST_URL, "Ingest");
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, INGEST_URL, "Ingest");
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, INGEST_URL, "Ingest");
}
