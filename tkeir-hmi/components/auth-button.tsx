"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LogIn, LogOut, User } from "lucide-react";

import { Button } from "@/components/ui/button";

interface SessionInfo {
  authEnabled: boolean;
  authenticated: boolean;
  user: { name?: string | null; email?: string | null } | null;
}

/** Sign-in / sign-out controls when AUTH_ENABLED=true. */
export function AuthButton() {
  const [info, setInfo] = useState<SessionInfo | null>(null);

  useEffect(() => {
    void fetch("/api/auth/session-info", { cache: "no-store" })
      .then((r) => r.json())
      .then((data: SessionInfo) => setInfo(data))
      .catch(() => setInfo({ authEnabled: false, authenticated: false, user: null }));
  }, []);

  if (!info?.authEnabled) {
    return null;
  }

  if (!info.authenticated) {
    return (
      <Button variant="outline" size="sm" asChild>
        <Link href="/api/auth/signin">
          <LogIn className="mr-1.5 h-4 w-4" />
          Sign in
        </Link>
      </Button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
        <User className="h-3.5 w-3.5" />
        {info.user?.name || info.user?.email || "Signed in"}
      </span>
      <Button variant="outline" size="sm" asChild>
        <Link href="/api/auth/signout">
          <LogOut className="mr-1.5 h-4 w-4" />
          Sign out
        </Link>
      </Button>
    </div>
  );
}
