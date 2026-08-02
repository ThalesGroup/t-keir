import { NextResponse } from "next/server";

/**
 * Auth enforcement is handled client-side via keycloak-js + RequireRole.
 *
 * The Next.js middleware is kept as a no-op so we don't conflict with
 * keycloak-js redirects / token refresh.
 */
export default function middleware() {
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
