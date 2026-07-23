"use client";

import { AlertTriangle } from "lucide-react";

import { AgentDialog } from "@/components/agent-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface AgentPanelProps {
  available: boolean;
}

export function AgentPanel({ available }: AgentPanelProps) {
  if (!available) {
    return (
      <div className="mx-auto max-w-3xl">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Agent service unavailable</AlertTitle>
          <AlertDescription>
            Start{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              make agent
            </code>{" "}
            (default port 8092), then refresh this page.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">Agent dialog</h2>
        <p className="text-sm text-muted-foreground">
          Discuss with researcher or multi-agent workflows, then compose a
          custom grounded report from your data.
        </p>
      </div>
      <div className="rounded-xl border bg-card p-4 shadow-sm">
        <AgentDialog className="min-h-[28rem]" />
      </div>
      <p className="text-xs text-muted-foreground">
        Tip: open{" "}
        <a href="/agents" className="underline underline-offset-2">
          /agents
        </a>{" "}
        to monitor run status and publish composed markdown.
      </p>
    </div>
  );
}
