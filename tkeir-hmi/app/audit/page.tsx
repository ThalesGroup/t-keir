import { AuditReportPanel } from "@/components/audit-report-panel";
import { RequireRole } from "@/src/auth/RequireRole";
import { personaPageRoles } from "@/lib/usecase-roles";

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
    <RequireRole allowedRoles={personaPageRoles()}>
      <div className="w-full space-y-6 px-4 py-8 sm:px-8 lg:px-10">
        <div>
          <p className="text-sm font-semibold uppercase tracking-wider text-primary">
            T-KEIR
          </p>
          <h1 className="text-3xl font-bold tracking-tight">Audit trail</h1>
          <p className="mt-1 text-base text-muted-foreground">
            Actions recorded for this answer&apos;s correlation id. You can
            return to search without signing in again.
          </p>
        </div>
        <AuditReportPanel correlationId={cid} />
      </div>
    </RequireRole>
  );
}
