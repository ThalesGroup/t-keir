import { NextRequest } from "next/server";

import { proxyUpstream } from "@/lib/admin-proxy";

const AUDIT_URL = process.env.AUDIT_URL ?? "http://localhost:8093";

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, AUDIT_URL, "Audit");
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, AUDIT_URL, "Audit");
}
