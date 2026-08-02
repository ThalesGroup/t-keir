"use client";

import React, { createContext, useContext, useEffect, useMemo, useState } from "react";

import {
  getRoles,
  getClearance,
  isAuthenticated,
  getAccessToken,
  login,
  logout,
  initKeycloak,
  ensureTokenFresh,
  resetKeycloak,
} from "./keycloak";
import type { RuntimeConfig } from "../config/runtimeConfig";
import { loadRuntimeConfig } from "../config/runtimeConfig";
import { LoginGate } from "./LoginGate";

export type Clearance = "UNCLASSIFIED" | "FOUO" | "SECRET";

export type PersonaId = "analyst" | "moc-watch" | "humint" | "commander" | "admin";

type PersonaDef = {
  id: PersonaId;
  label: string;
  roles: string[];
};

const PERSONAS: PersonaDef[] = [
  { id: "analyst", label: "Analyst", roles: ["c2-j2-analyst"] },
  { id: "moc-watch", label: "MOC Watch", roles: ["c2-moc-watch"] },
  { id: "humint", label: "HUMINT", roles: ["c2-j2x-humint"] },
  { id: "commander", label: "Commander", roles: ["c2-ctf-commander"] },
  // Admin persona is allowed to operate kill switches.
  { id: "admin", label: "Admin", roles: ["c2-admin", "tkeir-admin"] },
];

type AuthState = {
  authEnabled: boolean;
  initializing: boolean;
  authenticated: boolean;
  roles: string[];
  clearance: Clearance | null;
  personas: PersonaDef[];
  activePersonaId: PersonaId | null;
  setActivePersonaId: (id: PersonaId) => void;
  accessToken: string | null;
  runtimeConfig: RuntimeConfig | null;
  authError: string | null;
  loginWithRedirect: (path: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

function formatAuthError(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Keycloak initialization failed.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig | null>(null);
  const [authEnabled, setAuthEnabled] = useState<boolean>(true);
  const [initializing, setInitializing] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const [authenticated, setAuthenticated] = useState(false);
  const [roles, setRoles] = useState<string[]>([]);
  const [clearance, setClearanceState] = useState<Clearance | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [loginInitiated, setLoginInitiated] = useState(false);
  const [activePersonaId, setActivePersonaIdState] = useState<PersonaId | null>(null);

  useEffect(() => {
    let cancelled = false;
    setInitializing(true);

    async function boot() {
      let cfg: RuntimeConfig | null = null;
      try {
        cfg = await loadRuntimeConfig();
        if (cancelled) return;
        setRuntimeConfig(cfg);
        setAuthEnabled(true);
        setAuthError(null);

        await initKeycloak(cfg);

        if (cancelled) return;
        setAuthenticated(isAuthenticated());
        setLoginInitiated(false);
        setRoles(getRoles());
        setClearanceState(getClearance());
        setAccessTokenState(getAccessToken());
      } catch (err) {
        if (cancelled) return;
        if (cfg) {
          setAuthEnabled(true);
          setAuthError(formatAuthError(err));
        } else {
          setRuntimeConfig(null);
          setAuthEnabled(false);
          setAuthError(null);
        }
        setAuthenticated(false);
        setRoles([]);
        setClearanceState(null);
        setAccessTokenState(null);
        setActivePersonaIdState(null);
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }

    void boot();
    return () => {
      cancelled = true;
    };
  }, []);

  // Hard ceiling: never leave the UI on "Checking session…" forever.
  useEffect(() => {
    if (!initializing) return;
    const t = window.setTimeout(() => {
      setInitializing(false);
      setAuthEnabled(true);
      setAuthError((prev) => prev ?? "Session check timed out — sign in to continue.");
    }, 10_000);
    return () => window.clearTimeout(t);
  }, [initializing]);

  const availablePersonas = useMemo(() => {
    if (!roles.length) return [];
    return PERSONAS.filter((p) => p.roles.some((r) => roles.includes(r)));
  }, [roles]);

  useEffect(() => {
    if (!authEnabled || !authenticated) return;
    if (availablePersonas.length === 0) {
      setActivePersonaIdState(null);
      return;
    }

    const stored =
      window.localStorage.getItem("tkeir_active_persona_id") as PersonaId | null;
    const storedOk = stored && availablePersonas.some((p) => p.id === stored);

    setActivePersonaIdState(storedOk ? stored : availablePersonas[0]?.id);
  }, [authEnabled, authenticated, availablePersonas]);

  function setActivePersonaId(id: PersonaId) {
    if (!availablePersonas.some((p) => p.id === id)) return;
    window.localStorage.setItem("tkeir_active_persona_id", id);
    setActivePersonaIdState(id);
  }

  useEffect(() => {
    if (!authEnabled || initializing) return;
    if (!authenticated) return;

    const t = window.setInterval(async () => {
      try {
        await ensureTokenFresh(60);
        setAccessTokenState(getAccessToken());
      } catch {
        // ignore (offline / unreachable; the UI already handles that elsewhere)
      }
    }, 45_000);
    return () => window.clearInterval(t);
  }, [authEnabled, authenticated, initializing]);

  async function loginWithRedirect(path: string) {
    sessionStorage.setItem("postLoginRedirect", path);
    setAuthError(null);
    setLoginInitiated(true);
    try {
      if (!runtimeConfig) {
        throw new Error("Missing /config.json (Keycloak settings).");
      }
      // Previous failed/timed-out init leaves a dead promise — force a fresh one.
      if (!isAuthenticated()) {
        resetKeycloak();
        await initKeycloak(runtimeConfig);
      }
      await login(window.location.origin + path, { prompt: "login" });
    } catch (err) {
      setAuthError(formatAuthError(err));
      setLoginInitiated(false);
    }
  }

  async function signOut() {
    setAuthenticated(false);
    setRoles([]);
    setClearanceState(null);
    setAccessTokenState(null);
    setActivePersonaIdState(null);
    setLoginInitiated(false);
    // Keycloak redirects back to "/" after ending SSO; do not force a local
    // navigation here (that used to cancel logout and keep the SSO session).
    await logout(window.location.origin + "/");
  }

  const value = useMemo<AuthState>(
    () => ({
      authEnabled,
      initializing,
      authenticated,
      roles,
      clearance,
      personas: availablePersonas,
      activePersonaId,
      setActivePersonaId,
      accessToken,
      runtimeConfig,
      authError,
      loginWithRedirect,
      signOut,
    }),
    [
      authEnabled,
      initializing,
      authenticated,
      roles,
      clearance,
      availablePersonas,
      activePersonaId,
      accessToken,
      runtimeConfig,
      authError,
    ],
  );

  const topLabel = clearance ? `Clearance: ${clearance}` : "Clearance: UNAVAILABLE";
  const showLoginGate =
    authEnabled && !initializing && !authenticated;

  return (
    <AuthCtx.Provider value={value}>
      <div className="fixed left-0 right-0 top-0 z-50 border-b bg-card/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6">
          <div className="text-xs font-semibold uppercase tracking-wider text-primary">
            {topLabel}
          </div>
          {authenticated && availablePersonas.length > 1 ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Persona</span>
              <select
                value={activePersonaId ?? ""}
                onChange={(e) => setActivePersonaId(e.target.value as PersonaId)}
                className="rounded-md border bg-background px-2 py-1 text-xs outline-none focus:ring-2 focus:ring-ring"
              >
                {availablePersonas.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 z-40 border-t bg-card/85 backdrop-blur">
        <div className="mx-auto px-4 py-2 text-center text-[11px] text-muted-foreground sm:px-6">
          Access ceiling enforced to:{" "}
          <span className="font-semibold">{clearance ?? "N/A"}</span>
        </div>
      </div>

      <div className="min-h-screen pt-10 pb-12">
        {initializing ? (
          <div className="flex min-h-[70vh] items-center justify-center text-sm text-muted-foreground">
            Checking session…
          </div>
        ) : showLoginGate ? (
          <LoginGate
            error={authError}
            busy={loginInitiated && !authError}
            onSignIn={() =>
              void loginWithRedirect(
                window.location.pathname + window.location.search,
              )
            }
          />
        ) : (
          children
        )}
      </div>
    </AuthCtx.Provider>
  );
}
