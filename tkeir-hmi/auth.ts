import NextAuth from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

/**
 * Auth.js (next-auth v5) — Keycloak realm `tkeir`, public client `tkeir-hmi`
 * with Authorization Code + PKCE.
 *
 * When `AUTH_ENABLED` is not `"true"`, providers are empty so P0 `npm run
 * dev` stays anonymous.
 */
const authEnabled = process.env.AUTH_ENABLED === "true";

function decodeJwtPayload(token: string): Record<string, unknown> {
  const segment = token.split(".")[1];
  if (!segment) {
    return {};
  }
  const padded = segment.padEnd(segment.length + ((4 - (segment.length % 4)) % 4), "=");
  const json = Buffer.from(padded.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString(
    "utf8",
  );
  try {
    return JSON.parse(json) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function realmRoles(payload: Record<string, unknown>): string[] {
  const realmAccess = payload.realm_access;
  if (
    realmAccess &&
    typeof realmAccess === "object" &&
    "roles" in realmAccess &&
    Array.isArray((realmAccess as { roles?: unknown }).roles)
  ) {
    return (realmAccess as { roles: string[] }).roles;
  }
  return [];
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: authEnabled
    ? [
        Keycloak({
          clientId: process.env.AUTH_KEYCLOAK_ID ?? "tkeir-hmi",
          // Public client — empty secret; PKCE is used.
          clientSecret: process.env.AUTH_KEYCLOAK_SECRET ?? "",
          issuer:
            process.env.AUTH_KEYCLOAK_ISSUER ??
            "http://localhost:8082/realms/tkeir",
        }),
      ]
    : [],
  session: { strategy: "jwt" },
  callbacks: {
    async jwt({ token, account }) {
      if (account?.access_token) {
        token.accessToken = account.access_token;
        token.roles = realmRoles(decodeJwtPayload(account.access_token));
      }
      if (account?.id_token) {
        token.idToken = account.id_token;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken =
        typeof token.accessToken === "string" ? token.accessToken : undefined;
      session.roles = Array.isArray(token.roles) ? token.roles : [];
      return session;
    },
  },
  trustHost: true,
});
