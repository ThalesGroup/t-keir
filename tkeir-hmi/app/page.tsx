import { RagDashboard } from "@/components/rag-dashboard";
import { RequireRole } from "@/src/auth/RequireRole";
import { personaPageRoles } from "@/lib/usecase-roles";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const params = await searchParams;

  return (
    <RequireRole allowedRoles={personaPageRoles()}>
      <RagDashboard initialMode={params.mode} />
    </RequireRole>
  );
}
