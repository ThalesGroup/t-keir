"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "./AuthProvider";

export function RequireRole({
  allowedRoles,
  children,
  fallbackPath = "/no-entitlement",
}: {
  allowedRoles: string[];
  children: React.ReactNode;
  fallbackPath?: string;
}) {
  const router = useRouter();
  const { authEnabled, initializing, authenticated, roles } = useAuth();

  useEffect(() => {
    if (!authEnabled) return;
    if (initializing) return;
    if (!authenticated) return;
    const ok = allowedRoles.some((r) => roles.includes(r));
    if (!ok) router.replace(fallbackPath);
  }, [authEnabled, initializing, authenticated, allowedRoles, roles, fallbackPath, router]);

  if (!authEnabled) return <>{children}</>;
  if (initializing) return <div className="p-6 text-sm">Signing in…</div>;
  if (!authenticated) return <div className="p-6 text-sm">Redirecting to Keycloak…</div>;

  const ok = allowedRoles.some((r) => roles.includes(r));
  if (!ok) return <div className="p-6 text-sm">No entitlement.</div>;

  return <>{children}</>;
}

