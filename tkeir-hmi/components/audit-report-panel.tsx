"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { apiFetch } from "@/src/auth/useApiClient";

interface AuditReport {
  correlation_id: string;
  action_count: number;
  actions: Array<Record<string, unknown>>;
}

/** Read-only audit trail for a search/RAG correlation id. */
export function AuditReportPanel({
  correlationId,
}: {
  correlationId: string | null;
}) {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!correlationId) {
      setReport(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setReport(null);
    void (async () => {
      try {
        // Do not force Keycloak re-login on optional audit 401/503 — the
        // search session must stay intact when audit profile is down.
        const res = await apiFetch(
          `/api/audit/audit/report?correlation_id=${encodeURIComponent(correlationId)}`,
          { cache: "no-store" },
          { retryOn401: false },
        );
        if (cancelled) {
          return;
        }
        if (res.status === 401 || res.status === 403) {
          setError(
            "Audit service rejected the request (auth). You are still signed in to search.",
          );
          return;
        }
        if (res.status === 404 || res.status === 503) {
          setError(
            "Audit report unavailable. Start the audit profile (PROFILES=core,audit) and retry.",
          );
          return;
        }
        if (!res.ok) {
          setError(`Audit report failed (${res.status}).`);
          return;
        }
        setReport((await res.json()) as AuditReport);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "audit load failed");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [correlationId]);

  if (!correlationId) {
    return (
      <p className="text-sm text-muted-foreground">
        No correlation id. Run a search or RAG query, then use{" "}
        <em>Audit this answer</em>.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border bg-card p-4">
        <h2 className="text-base font-semibold">Correlation</h2>
        <code className="mt-2 block break-all rounded bg-muted/50 px-2 py-1 font-mono text-xs">
          {correlationId}
        </code>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button asChild variant="outline" size="sm">
            <Link href="/">← Back to search</Link>
          </Button>
          <Button asChild variant="ghost" size="sm">
            <Link href={`/admin?correlation_id=${encodeURIComponent(correlationId)}`}>
              Admin oversight
            </Link>
          </Button>
        </div>
      </div>

      <div className="rounded-md border bg-card p-4">
        <h2 className="text-base font-semibold">Audit report</h2>
        {loading ? (
          <p className="mt-2 text-sm text-muted-foreground">Loading…</p>
        ) : null}
        {error ? (
          <p className="mt-2 text-sm text-amber-700 dark:text-amber-300">
            {error}
          </p>
        ) : null}
        {report ? (
          <>
            <p className="mt-2 text-sm text-muted-foreground">
              {report.action_count} action
              {report.action_count === 1 ? "" : "s"} recorded
            </p>
            <pre className="mt-3 max-h-[32rem] overflow-auto rounded bg-muted/40 p-3 text-xs leading-relaxed">
              {JSON.stringify(report, null, 2)}
            </pre>
          </>
        ) : null}
      </div>
    </div>
  );
}
