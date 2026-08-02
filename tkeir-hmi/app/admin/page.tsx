import Link from "next/link";

import { AdminPanel } from "@/components/admin-panel";
import { RequireRole } from "@/src/auth/RequireRole";

/**
 * Oversight panel — kill switch, budgets, approvals (Phase 5).
 */
export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ correlation_id?: string }>;
}) {
  const params = await searchParams;
  const cid = params.correlation_id?.trim() || null;

  return (
    <RequireRole allowedRoles={["c2-admin", "tkeir-admin"]}>
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            T-KEIR
          </p>
          <h1 className="text-2xl font-bold tracking-tight">Admin oversight</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Runtime governor controls, budgets, and audit deep-links. Corpus
            ingest is in the workspace sidebar as Ingest.
          </p>
        </div>

        <AdminPanel correlationId={cid} isAdmin={true} />

        <Link
          href="/"
          className="text-sm text-primary underline-offset-2 hover:underline"
        >
          ← Back to search
        </Link>
      </div>
    </RequireRole>
  );
}
