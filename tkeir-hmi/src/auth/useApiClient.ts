import {
  ensureTokenFresh,
  getAccessToken,
  isAuthenticated,
  login,
} from "./keycloak";

/**
 * Fetch wrapper that attaches Bearer token from keycloak-js and retries once
 * on 401 by refreshing the token.
 *
 * Calls are expected to target the HMI proxy (`/api/...`) so the token is
 * forwarded to the backend upstream.
 */
export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  opts?: { retryOn401?: boolean },
): Promise<Response> {
  const retryOn401 = opts?.retryOn401 ?? true;

  const headers = new Headers(init.headers ?? {});
  const token = isAuthenticated() ? getAccessToken() : null;
  if (token && !headers.has("authorization")) {
    headers.set("authorization", `Bearer ${token}`);
  }
  const personaId = window.localStorage.getItem("tkeir_active_persona_id");
  if (personaId && !headers.has("x-persona-id")) {
    headers.set("x-persona-id", personaId);
  }

  const res = await fetch(input, { ...init, headers });
  if (!retryOn401 || res.status !== 401) return res;

  const fresh = await ensureTokenFresh(60);
  if (!fresh) {
    await login(window.location.href);
    return res;
  }

  const retryHeaders = new Headers(init.headers ?? {});
  retryHeaders.set("authorization", `Bearer ${fresh}`);
  const retryRes = await fetch(input, { ...init, headers: retryHeaders });
  if (retryRes.status === 401) {
    await login(window.location.href);
  }
  return retryRes;
}

export async function apiPostJson<T>(
  url: string,
  body: unknown,
): Promise<T> {
  const res = await apiFetch(
    url,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    },
    { retryOn401: true },
  );
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const payload = (await res.json()) as { detail?: string };
      if (payload.detail) detail = payload.detail;
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

