import { NextRequest } from "next/server";

import { proxyUpstream } from "@/lib/admin-proxy";

const OKF_URL = process.env.OKF_URL ?? "http://localhost:8094";

type RouteContext = { params: Promise<{ path?: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, OKF_URL, "OKF");
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, OKF_URL, "OKF");
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return proxyUpstream(request, path, OKF_URL, "OKF");
}
