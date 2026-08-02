"use client";

import { LogIn, LogOut, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/src/auth/AuthProvider";

/** Sign-in / sign-out controls when AUTH_ENABLED=true. */
export function AuthButton() {
  const {
    authEnabled,
    initializing,
    authenticated,
    roles,
    clearance,
    loginWithRedirect,
    signOut,
  } = useAuth();

  if (!authEnabled) return null;

  if (initializing || !authenticated) {
    return (
      <Button
        variant="outline"
        size="sm"
        onClick={() =>
          void loginWithRedirect(
            window.location.pathname + window.location.search,
          )
        }
        disabled={initializing}
      >
        <LogIn className="mr-1.5 h-4 w-4" />
        Sign in
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
        <User className="h-3.5 w-3.5" />
        {roles.includes("c2-admin") || roles.includes("tkeir-admin")
          ? "Admin"
          : "User"}
        {clearance ? ` (${clearance})` : ""}
      </span>
      <Button variant="outline" size="sm" onClick={() => void signOut()}>
        <LogOut className="mr-1.5 h-4 w-4" />
        Sign out
      </Button>
    </div>
  );
}
