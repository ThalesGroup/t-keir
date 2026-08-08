import Link from "next/link";

import { AgentRunMonitor } from "@/components/agent-run-monitor";
import { RequireRole } from "@/src/auth/RequireRole";

/**
 * Minimal agent / workflow run monitor (Phase E).
 */
export default function AgentsPage() {
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
          <h1 className="text-2xl font-bold tracking-tight">Agent runs</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Start a workflow, poll status / handoffs / compose output, and publish
            through the approval-gated re-ingest path.
          </p>
        </div>

        <AgentRunMonitor />

        <div className="rounded-xl border bg-card p-4 text-sm shadow-sm">
          <h2 className="font-semibold">Workflow cards</h2>
          <ul className="mt-2 space-y-2 text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">persona_*</span> —
              default per Keycloak persona (analyse → review → write → OTAN
              compose):{" "}
              <code>persona_j2_analyst</code>, <code>persona_moc_watch</code>,{" "}
              <code>persona_j2x_humint</code>,{" "}
              <code>persona_ctf_commander</code>, <code>persona_admin</code>
            </li>
            <li>
              <span className="font-medium text-foreground">rag_with_wiki</span>{" "}
              — search chunks → wiki_upsert (reuse closest OKF via index.md) →
              answer_generate (compose template e.g.{" "}
              <code>otan_sitrep</code>)
            </li>
            <li>
              <span className="font-medium text-foreground">llm_wiki</span> —
              single-pass wiki_upsert with persona <code>*_prompt</code>{" "}
              (Reporter Grab path; legacy iterative only with{" "}
              <code>wiki_mode=iterative</code>)
            </li>
            <li>
              <span className="font-medium text-foreground">otan_c2_brief</span>{" "}
              — shared OTAN + LLM Wiki pipeline (researcher → reviewer →
              wiki_writer)
            </li>
            <li>
              <span className="font-medium text-foreground">okf_wiki_brief</span>{" "}
              — scoped OKF export → okf_curator → synthesis_note
            </li>
          </ul>
        </div>

        <div className="flex gap-4 text-sm">
          <Link
            href="/"
            className="text-primary underline-offset-2 hover:underline"
          >
            ← Search
          </Link>
          <Link
            href="/?mode=wiki"
            className="text-primary underline-offset-2 hover:underline"
          >
            LLM Wiki
          </Link>
          <Link
            href="/admin"
            className="text-primary underline-offset-2 hover:underline"
          >
            Admin / approvals
          </Link>
        </div>
      </div>
    </RequireRole>
  );
}
