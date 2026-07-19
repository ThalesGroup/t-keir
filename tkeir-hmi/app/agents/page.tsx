import Link from "next/link";

import { AgentRunMonitor } from "@/components/agent-run-monitor";

/**
 * Minimal agent / workflow run monitor (Phase E).
 */
export default function AgentsPage() {
  return (
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

      <div className="flex gap-4 text-sm">
        <Link
          href="/"
          className="text-primary underline-offset-2 hover:underline"
        >
          ← Search
        </Link>
        <Link
          href="/admin"
          className="text-primary underline-offset-2 hover:underline"
        >
          Admin / approvals
        </Link>
      </div>
    </div>
  );
}
