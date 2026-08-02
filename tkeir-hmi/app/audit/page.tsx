import { AuditReportPanel } from "@/components/audit-report-panel";
import { RequireRole } from "@/src/auth/RequireRole";

/**
 * Persona-accessible audit trail for a search/RAG correlation id.
 * (Admin kill-switch / budgets stay on /admin.)
 */
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ correlation_id?: string }>;
}) {
  const params = await searchParams;
  const cid = params.correlation_id?.trim() || null;

  return (
    <RequireRole
      allowedRoles={[
        "c2-j2-analyst",
        "c2-moc-watch",
        "c2-j2x-humint",
        "c2-ctf-commander",
        "c2-admin",
        "tkeir-admin",
      ]}
    >
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-10">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-primary">
            T-KEIR
          </p>
          <h1 className="text-2xl font-bold tracking-tight">Audit trail</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Actions recorded for this answer&apos;s correlation id. You can
            return to search without signing in again.
          </p>
        </div>
        <AuditReportPanel correlationId={cid} />
      </div>
    </RequireRole>
  );
}
