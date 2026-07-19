"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type RunPayload = {
  run?: {
    run_id?: string;
    status?: string;
    goal?: string;
    workflow?: string | null;
    agent?: string;
    error?: string | null;
    correlation_id?: string;
    usage?: Record<string, number>;
  };
  steps?: Array<{
    step_index: number;
    status: string;
    tool_call?: { name: string } | null;
    thought_excerpt?: string;
  }>;
  handoffs?: Array<{
    from_agent: string;
    to_agent: string;
    reason: string;
  }>;
  compose_result?: {
    markdown?: string;
    citations_map?: Record<string, string[]>;
    unfilled?: string[];
  } | null;
};

export function AgentRunMonitor() {
  const [goal, setGoal] = useState("Profile Acme");
  const [topic, setTopic] = useState("Acme");
  const [workflow, setWorkflow] = useState("content_brief");
  const [workflows, setWorkflows] = useState<string[]>(["content_brief"]);
  const [runId, setRunId] = useState<string | null>(null);
  const [payload, setPayload] = useState<RunPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [publishMsg, setPublishMsg] = useState<string | null>(null);
  const [approvalId, setApprovalId] = useState<string | null>(null);

  useEffect(() => {
    void fetch("/api/agent/agent/workflows", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) {
          return;
        }
        const body = (await res.json()) as { workflows?: string[] };
        if (body.workflows?.length) {
          setWorkflows(body.workflows);
          setWorkflow(body.workflows[0]);
        }
      })
      .catch(() => undefined);
  }, []);

  const refresh = useCallback(async (id: string) => {
    const res = await fetch(`/api/agent/agent/runs/${encodeURIComponent(id)}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(detail || `status ${res.status}`);
    }
    setPayload((await res.json()) as RunPayload);
  }, []);

  useEffect(() => {
    if (!runId) {
      return;
    }
    const tick = () => {
      void refresh(runId).catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "poll failed");
      });
    };
    tick();
    const timer = window.setInterval(tick, 1500);
    return () => window.clearInterval(timer);
  }, [runId, refresh]);

  const status = payload?.run?.status ?? null;
  const terminal = useMemo(
    () =>
      status === "succeeded" ||
      status === "failed" ||
      status === "blocked" ||
      status === "killed" ||
      status === "cancelled",
    [status],
  );

  async function startRun() {
    setBusy(true);
    setError(null);
    setPublishMsg(null);
    setApprovalId(null);
    setPayload(null);
    try {
      const res = await fetch("/api/agent/agent/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          workflow,
          goal: goal.trim(),
          params: { topic: topic.trim() || goal.trim() },
        }),
      });
      const body = (await res.json()) as {
        run_id?: string;
        detail?: string;
      };
      if (!res.ok || !body.run_id) {
        throw new Error(body.detail || `start failed (${res.status})`);
      }
      setRunId(body.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to start run");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!runId) {
      return;
    }
    setBusy(true);
    setPublishMsg(null);
    setError(null);
    try {
      const res = await fetch(
        `/api/agent/agent/runs/${encodeURIComponent(runId)}/publish`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(
            approvalId ? { approval_id: approvalId } : {},
          ),
        },
      );
      const body = (await res.json()) as {
        status?: string;
        approval_id?: string;
        detail?: string;
        origin?: string;
        markdown_path?: string;
        error?: string;
      };
      if (!res.ok) {
        throw new Error(body.detail || body.error || `publish ${res.status}`);
      }
      if (body.approval_id) {
        setApprovalId(body.approval_id);
      }
      if (body.status === "awaiting_approval") {
        setPublishMsg(
          `Awaiting approval ${body.approval_id}. Approve it in /admin, then click Publish again.`,
        );
      } else if (body.status === "published") {
        setPublishMsg(
          `Published (${body.origin}). Staged at ${body.markdown_path}`,
        );
      } else {
        setPublishMsg(JSON.stringify(body));
      }
      await refresh(runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "publish failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <section className="rounded-xl border bg-card p-4 shadow-sm space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Start workflow
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Goal</span>
            <Input
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-muted-foreground">Topic</span>
            <Input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              disabled={busy}
            />
          </label>
          <label className="space-y-1 text-sm sm:col-span-2">
            <span className="text-muted-foreground">Workflow</span>
            <select
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              value={workflow}
              onChange={(e) => setWorkflow(e.target.value)}
              disabled={busy}
            >
              {workflows.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void startRun()} disabled={busy || !goal.trim()}>
            Start run
          </Button>
          <Button
            variant="outline"
            onClick={() => runId && void refresh(runId)}
            disabled={!runId || busy}
          >
            Refresh
          </Button>
          <Button
            variant="secondary"
            onClick={() => void publish()}
            disabled={!runId || status !== "succeeded" || busy}
          >
            Publish
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Publish is gated by the governor ApprovalQueue in enforce mode. Use{" "}
          <Link href="/admin" className="underline underline-offset-2">
            /admin
          </Link>{" "}
          to approve, then publish again.
        </p>
      </section>

      {error ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {publishMsg ? (
        <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
          {publishMsg}
        </p>
      ) : null}

      {runId ? (
        <section className="rounded-xl border bg-card p-4 shadow-sm space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Run monitor
            </h2>
            <code className="text-xs text-muted-foreground">{runId}</code>
          </div>
          <dl className="grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted-foreground">Status</dt>
              <dd className="font-medium">
                {status ?? "…"}
                {terminal ? "" : " (polling)"}
              </dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Agent / workflow</dt>
              <dd>
                {payload?.run?.agent ?? "—"} / {payload?.run?.workflow ?? "—"}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted-foreground">Goal</dt>
              <dd>{payload?.run?.goal ?? goal}</dd>
            </div>
            {payload?.run?.error ? (
              <div className="sm:col-span-2 text-destructive">
                {payload.run.error}
              </div>
            ) : null}
          </dl>

          {payload?.handoffs?.length ? (
            <div>
              <h3 className="mb-1 text-sm font-medium">Handoffs</h3>
              <ul className="space-y-1 text-sm text-muted-foreground">
                {payload.handoffs.map((h, i) => (
                  <li key={`${h.from_agent}-${h.to_agent}-${i}`}>
                    {h.from_agent} → {h.to_agent}{" "}
                    <span className="opacity-70">({h.reason})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {payload?.steps?.length ? (
            <div>
              <h3 className="mb-1 text-sm font-medium">Steps</h3>
              <ul className="max-h-48 space-y-1 overflow-y-auto text-xs font-mono">
                {payload.steps.map((s) => (
                  <li key={s.step_index}>
                    [{s.step_index}] {s.status}
                    {s.tool_call?.name ? ` tool=${s.tool_call.name}` : ""}
                    {s.thought_excerpt
                      ? ` — ${s.thought_excerpt.slice(0, 80)}`
                      : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {payload?.compose_result?.markdown ? (
            <div>
              <h3 className="mb-1 text-sm font-medium">Compose preview</h3>
              <pre className="max-h-80 overflow-auto rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap">
                {payload.compose_result.markdown}
              </pre>
              {payload.compose_result.unfilled?.length ? (
                <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                  Unfilled: {payload.compose_result.unfilled.join("; ")}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
