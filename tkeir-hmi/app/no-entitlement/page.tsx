"use client";

import Link from "next/link";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/src/auth/AuthProvider";

export default function NoEntitlementPage() {
  const { signOut, clearance } = useAuth();

  return (
    <div className="mx-auto max-w-xl space-y-6 px-4 py-12">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">
          T-KEIR
        </p>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">
          No entitlement
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Your Keycloak roles don’t permit access to this workspace.
          {clearance ? ` Clearance: ${clearance}.` : null}
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/" className="text-sm text-primary underline-offset-2 hover:underline">
          Back to search
        </Link>
        <Button
          variant="outline"
          onClick={() => void signOut()}
        >
          Sign out
        </Button>
      </div>
    </div>
  );
}

