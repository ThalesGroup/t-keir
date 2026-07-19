import { NextResponse } from "next/server";

import { auth } from "@/auth";

export async function GET() {
  if (process.env.AUTH_ENABLED !== "true") {
    return NextResponse.json({
      authEnabled: false,
      authenticated: false,
    });
  }
  const session = await auth();
  return NextResponse.json({
    authEnabled: true,
    authenticated: Boolean(session?.user),
    user: session?.user
      ? {
          name: session.user.name,
          email: session.user.email,
        }
      : null,
  });
}
