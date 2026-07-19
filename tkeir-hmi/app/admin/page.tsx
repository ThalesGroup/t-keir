import Link from "next/link";

import { auth } from "@/auth";
import { AdminPanel } from "@/components/admin-panel";

function hasAdminRole(roles: string[] | undefined): boolean {
  return Boolean(roles?.includes("tkeir-admin"));
}

/**
 * Oversight panel — kill switch, budgets, approvals (Phase 5).
 */
export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ correlation_id?: string }>;
}) {
  const params = await searchParams;
  const session = await auth();
  const authEnabled = process.env.AUTH_ENABLED === "true";
  const cid = params.correlation_id?.trim() || null;
  const isAdmin = !authEnabled || hasAdminRole(session?.roles);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">
          T-KEIR
        </p>
        <h1 className="text-2xl font-bold tracking-tight">Admin oversight</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Runtime governor controls, budget gauges, and audit deep-links.
        </p>
      </div>

      {authEnabled && (
        <p className="rounded-md border bg-card px-3 py-2 text-sm">
          Session:{" "}
          {session?.user
            ? session.user.email || session.user.name || "authenticated"
            : "anonymous"}
          {session?.roles?.length ? (
            <span className="ml-2 text-muted-foreground">
              roles: {session.roles.join(", ")}
            </span>
          ) : null}
          {!isAdmin ? (
            <span className="mt-1 block text-amber-700">
              Read-only view — sign in as a user with role{" "}
              <code>tkeir-admin</code> to operate kill switches.
            </span>
          ) : null}
        </p>
      )}

      <AdminPanel correlationId={cid} isAdmin={isAdmin} />

      <Link
        href="/"
        className="text-sm text-primary underline-offset-2 hover:underline"
      >
        ← Back to search
      </Link>
    </div>
  );
}
