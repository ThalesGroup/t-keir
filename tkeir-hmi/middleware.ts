import { NextResponse } from "next/server";

import { auth } from "@/auth";

/**
 * When AUTH_ENABLED=true, require a session for interactive pages (not
 * `/api/healthz` or Auth.js routes). P0 leaves AUTH_ENABLED unset/false.
 */
export default auth((request) => {
  if (process.env.AUTH_ENABLED !== "true") {
    return NextResponse.next();
  }
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/api/auth") ||
    pathname.startsWith("/api/healthz") ||
    pathname === "/login"
  ) {
    return NextResponse.next();
  }
  if (!request.auth) {
    const login = new URL("/api/auth/signin", request.nextUrl.origin);
    login.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(login);
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
