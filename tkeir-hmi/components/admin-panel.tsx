"use client";

import { useCallback, useEffect, useState } from "react";

type KillScope = "all" | "ingest" | "index" | "inference" | "hmi-write" | "agents";

interface KillSwitchState {
  active: boolean;
  reason: string;
  activated_at: string;
  activated_by: string;
}

interface RuntimeFlags {
  updated_at: string;
  scopes: Record<KillScope, KillSwitchState>;
}

interface BudgetSnapshot {
  actor_id: string;
  unit: string;
  limit: number;
  consumed: number;
  ratio: number;
  throttled: boolean;
  blocked: boolean;
}

interface ApprovalItem {
  approval_id: string;
  correlation_id: string;
  actor_id: string;
  intent: string;
  reason: string;
  created_at: string;
  status: string;
}

interface AuditReport {
  correlation_id: string;
  action_count: number;
  actions: Array<Record<string, unknown>>;
}

const SCOPES: KillScope[] = [
  "all",
  "ingest",
  "index",
  "inference",
  "hmi-write",
  "agents",
];

export function AdminPanel({
  correlationId,
  isAdmin,
}: {
  correlationId: string | null;
  isAdmin: boolean;
}) {
  const [flags, setFlags] = useState<RuntimeFlags | null>(null);
  const [budgets, setBudgets] = useState<BudgetSnapshot[]>([]);
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [auditReport, setAuditReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const flagsRes = await fetch("/api/governor/governor/flags", {
        cache: "no-store",
      });
      if (flagsRes.ok) {
        setFlags((await flagsRes.json()) as RuntimeFlags);
      }
      if (isAdmin) {
        const budgetRes = await fetch("/api/governor/governor/budgets", {
          cache: "no-store",
        });
        if (budgetRes.ok) {
          const body = (await budgetRes.json()) as { items: BudgetSnapshot[] };
          setBudgets(body.items);
        }
        const approvalRes = await fetch("/api/governor/governor/approvals", {
          cache: "no-store",
        });
        if (approvalRes.ok) {
          setApprovals((await approvalRes.json()) as ApprovalItem[]);
        }
      }
      if (correlationId) {
        const auditRes = await fetch(
          `/api/audit/audit/report?correlation_id=${encodeURIComponent(correlationId)}`,
          { cache: "no-store" },
        );
        if (auditRes.ok) {
          setAuditReport((await auditRes.json()) as AuditReport);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    }
  }, [correlationId, isAdmin]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function toggleKill(scope: KillScope, active: boolean) {
    if (!isAdmin) {
      return;
    }
    setBusy(true);
    try {
      const response = await fetch("/api/governor/governor/kill", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scope, active, reason: "admin panel" }),
      });
      if (!response.ok) {
        throw new Error(`Kill switch failed (${response.status})`);
      }
      setFlags((await response.json()) as RuntimeFlags);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kill switch failed");
    } finally {
      setBusy(false);
    }
  }

  async function decideApproval(approvalId: string, decision: "approve" | "deny") {
    setBusy(true);
    try {
      const response = await fetch(
        `/api/governor/governor/approvals/${approvalId}/${decision}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ note: "admin panel" }),
        },
      );
      if (!response.ok) {
        throw new Error(`Approval ${decision} failed (${response.status})`);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval action failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {error ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      <section className="rounded-md border bg-card p-4">
        <h2 className="text-lg font-semibold">Kill switch</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Runtime flags updated at {flags?.updated_at ?? "—"}
        </p>
        <ul className="mt-3 space-y-2">
          {SCOPES.map((scope) => {
            const state = flags?.scopes?.[scope];
            const active = state?.active ?? false;
            return (
              <li
                key={scope}
                className="flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium">{scope}</span>
                  {active ? (
                    <span className="ml-2 text-destructive">ACTIVE</span>
                  ) : (
                    <span className="ml-2 text-muted-foreground">off</span>
                  )}
                  {state?.reason ? (
                    <p className="text-xs text-muted-foreground">{state.reason}</p>
                  ) : null}
                </div>
                {isAdmin ? (
                  <button
                    type="button"
                    disabled={busy}
                    className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
                    onClick={() => void toggleKill(scope, !active)}
                  >
                    {active ? "Release" : "Kill"}
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      {isAdmin ? (
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-lg font-semibold">Budgets</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {budgets.map((budget) => (
              <li key={`${budget.actor_id}-${budget.unit}`} className="rounded border px-3 py-2">
                <span className="font-medium">{budget.unit}</span> —{" "}
                {budget.consumed.toFixed(0)} / {budget.limit.toFixed(0)} (
                {(budget.ratio * 100).toFixed(1)}%)
                {budget.blocked ? (
                  <span className="ml-2 text-destructive">blocked</span>
                ) : budget.throttled ? (
                  <span className="ml-2 text-amber-600">throttled</span>
                ) : null}
              </li>
            ))}
            {budgets.length === 0 ? (
              <li className="text-muted-foreground">No budget data yet.</li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {isAdmin ? (
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-lg font-semibold">Approvals</h2>
          <ul className="mt-3 space-y-2 text-sm">
            {approvals
              .filter((item) => item.status === "pending")
              .map((item) => (
                <li key={item.approval_id} className="rounded border px-3 py-2">
                  <p className="font-medium">{item.intent}</p>
                  <p className="text-xs text-muted-foreground">{item.reason}</p>
                  <code className="mt-1 block break-all text-xs">
                    {item.correlation_id}
                  </code>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground"
                      onClick={() => void decideApproval(item.approval_id, "approve")}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      className="rounded border px-2 py-1 text-xs"
                      onClick={() => void decideApproval(item.approval_id, "deny")}
                    >
                      Deny
                    </button>
                  </div>
                </li>
              ))}
            {approvals.filter((item) => item.status === "pending").length === 0 ? (
              <li className="text-muted-foreground">No pending approvals.</li>
            ) : null}
          </ul>
        </section>
      ) : null}

      {correlationId ? (
        <section className="rounded-md border bg-card p-4">
          <h2 className="text-lg font-semibold">Audit report</h2>
          <code className="mt-1 block break-all text-xs">{correlationId}</code>
          {auditReport ? (
            <pre className="mt-3 max-h-96 overflow-auto rounded bg-muted/40 p-3 text-xs">
              {JSON.stringify(auditReport, null, 2)}
            </pre>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">
              Start the audit profile to load reports (
              <code>PROFILES=core,audit</code>).
            </p>
          )}
        </section>
      ) : null}
    </div>
  );
}
