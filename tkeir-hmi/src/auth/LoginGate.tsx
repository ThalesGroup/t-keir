"use client";

import { LogIn, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";

const DEMO_ACCOUNTS = [
  { user: "analyst", password: "analyst", clearance: "SECRET", role: "J2 Analyst" },
  { user: "moc-watch", password: "moc-watch", clearance: "FOUO", role: "MOC Watch" },
  { user: "humint", password: "humint", clearance: "SECRET", role: "HUMINT" },
  { user: "commander", password: "commander", clearance: "SECRET", role: "Commander" },
  { user: "c2-admin", password: "c2-admin", clearance: "SECRET", role: "Admin" },
] as const;

export function LoginGate({
  error,
  onSignIn,
  busy,
}: {
  error?: string | null;
  onSignIn: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">T-KEIR</h1>
          <p className="text-sm text-muted-foreground">
            Sign in with Keycloak to continue. Username and password are entered
            on the identity provider page.
          </p>
        </div>

        {error ? (
          <div className="flex gap-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-3 text-sm text-destructive-foreground">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="space-y-1">
              <p className="font-medium text-destructive">Cannot reach Keycloak</p>
              <p className="text-muted-foreground">{error}</p>
              <p className="text-muted-foreground">
                Ensure Keycloak is running (`make keycloak-up`) and open the app
                at <code className="text-xs">http://localhost:3000</code>.
              </p>
            </div>
          </div>
        ) : null}

        <Button
          className="w-full"
          size="lg"
          onClick={onSignIn}
          disabled={busy}
        >
          <LogIn className="mr-2 h-4 w-4" />
          {busy ? "Opening Keycloak…" : "Sign in"}
        </Button>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Demo accounts
          </p>
          <div className="overflow-hidden rounded-md border text-sm">
            <table className="w-full">
              <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-3 py-2 font-medium">User</th>
                  <th className="px-3 py-2 font-medium">Password</th>
                  <th className="px-3 py-2 font-medium">Clearance</th>
                </tr>
              </thead>
              <tbody>
                {DEMO_ACCOUNTS.map((a) => (
                  <tr key={a.user} className="border-t">
                    <td className="px-3 py-2 font-mono text-xs">{a.user}</td>
                    <td className="px-3 py-2 font-mono text-xs">{a.password}</td>
                    <td className="px-3 py-2 text-xs">{a.clearance}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted-foreground">
            Password equals username for each demo account.
          </p>
        </div>
      </div>
    </div>
  );
}
