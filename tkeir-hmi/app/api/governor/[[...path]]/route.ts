import { NextRequest } from "next/server";

import { proxyUpstream } from "@/lib/admin-proxy";

const GOVERNOR_URL =
  process.env.GOVERNOR_URL ?? "http://localhost:8094";

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, GOVERNOR_URL, "Governor");
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, GOVERNOR_URL, "Governor");
}
