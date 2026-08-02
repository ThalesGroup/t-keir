import { RagDashboard } from "@/components/rag-dashboard";
import { RequireRole } from "@/src/auth/RequireRole";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const params = await searchParams;

  return (
    <RequireRole
      allowedRoles={[
        // Persona roles (per brief)
        "c2-j2-analyst",
        "c2-moc-watch",
        "c2-j2x-humint",
        "c2-ctf-commander",
        "c2-admin",
        // Backward-compatible admin role
        "tkeir-admin",
      ]}
    >
      <RagDashboard initialMode={params.mode} />
    </RequireRole>
  );
}
