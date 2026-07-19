import { NextRequest } from "next/server";

import { proxyUpstream } from "@/lib/admin-proxy";

const AGENT_URL = process.env.AGENT_URL ?? "http://localhost:8092";

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, AGENT_URL, "Agent");
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, AGENT_URL, "Agent");
}
