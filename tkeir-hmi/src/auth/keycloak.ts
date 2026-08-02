import Keycloak from "keycloak-js";

import type { RuntimeConfig } from "../config/runtimeConfig";

export type Clearance = "UNCLASSIFIED" | "FOUO" | "SECRET";

let kc: Keycloak | null = null;
let initPromise: Promise<Keycloak | null> | null = null;

const INIT_TIMEOUT_MS = 8_000;

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        window.clearTimeout(timer);
        reject(err);
      },
    );
  });
}

export function getKeycloakInstance(): Keycloak | null {
  return kc;
}

export function resetKeycloak(): void {
  kc = null;
  initPromise = null;
}

export async function initKeycloak(cfg: RuntimeConfig): Promise<Keycloak | null> {
  if (initPromise) return initPromise;

  initPromise = (async () => {
    try {
      kc = new Keycloak({
        url: cfg.keycloakUrl,
        realm: cfg.realm,
        clientId: cfg.clientId,
      });

      // Do NOT use silentCheckSsoRedirectUri: the hidden iframe often hangs
      // forever (3rd-party cookie / storage partitioning), leaving the UI on
      // "Checking session…". Init still processes ?code= after login redirect.
      await withTimeout(
        kc.init({
          pkceMethod: "S256",
          checkLoginIframe: false,
          enableLogging: process.env.NODE_ENV === "development",
        }),
        INIT_TIMEOUT_MS,
        `Keycloak did not respond within ${INIT_TIMEOUT_MS / 1000}s (is it running on ${cfg.keycloakUrl}?)`,
      );

      return kc;
    } catch (err) {
      kc = null;
      initPromise = null;
      throw err;
    }
  })();

  return initPromise;
}

export function getAccessToken(): string | null {
  return kc?.token ?? null;
}

export function getIdToken(): string | null {
  return kc?.idToken ?? null;
}

export function getRoles(): string[] {
  const parsed = (kc?.tokenParsed ?? {}) as Record<string, unknown>;
  const out = new Set<string>();

  const addAll = (value: unknown) => {
    if (!Array.isArray(value)) return;
    for (const item of value) {
      if (typeof item === "string" && item.trim()) out.add(item);
    }
  };

  const realmAccess = parsed.realm_access;
  if (realmAccess && typeof realmAccess === "object") {
    addAll((realmAccess as { roles?: unknown }).roles);
  }
  // Flat claim used by some Keycloak role mappers / client scopes.
  addAll(parsed.roles);
  // Mis-nested dotted claim name (literal key "realm_access.roles").
  addAll(parsed["realm_access.roles"]);

  return [...out];
}

export function getClearance(): Clearance | null {
  const clearance = (kc?.tokenParsed as any)?.clearance;
  if (clearance === "UNCLASSIFIED" || clearance === "FOUO" || clearance === "SECRET") {
    return clearance;
  }
  return null;
}

export function isAuthenticated(): boolean {
  return Boolean(kc?.authenticated);
}

export async function ensureTokenFresh(
  minValiditySeconds: number = 60,
): Promise<string | null> {
  if (!kc) return null;
  if (!kc.authenticated) return null;

  const expired = kc.isTokenExpired(minValiditySeconds);
  if (expired) {
    await kc.updateToken(minValiditySeconds);
  }
  return getAccessToken();
}

export function buildLoginRedirectUri(path: string): string {
  const url = new URL(window.location.origin);
  url.pathname = path;
  return url.toString();
}

export async function login(
  redirectUri: string,
  options?: { prompt?: "login" | "none" | "consent" },
) {
  if (!kc) throw new Error("Keycloak not initialized");
  // prompt=login forces the credential form so demo persona switching cannot
  // silently reuse a leftover SSO cookie.
  await kc.login({
    redirectUri,
    prompt: options?.prompt ?? "login",
  });
}

export async function logout(redirectUri: string) {
  if (!kc) {
    window.location.assign(redirectUri);
    return;
  }

  // Clear local demo state first; keep kc.idToken for the logout request.
  sessionStorage.removeItem("postLoginRedirect");
  window.localStorage.removeItem("tkeir_active_persona_id");

  // POST logout includes id_token_hint and ends the Keycloak SSO session.
  // Do NOT navigate afterward — that races location.replace/assign and leaves
  // the SSO cookie intact (next Sign in auto-logs the previous user back in).
  await kc.logout({
    redirectUri,
    logoutMethod: "POST",
  });

  // Adapter submits a form / redirects; if we somehow continue, stop here.
  await new Promise<never>(() => {});
}
