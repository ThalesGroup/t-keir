import { NextResponse } from "next/server";

/** Container / load-balancer liveness probe (no upstream RAG call). */
export async function GET() {
  return NextResponse.json({ status: "ok" }, { status: 200 });
}
