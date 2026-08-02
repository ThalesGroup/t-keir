"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiFetch } from "@/src/auth/useApiClient";

type IndexTarget = "global" | "user" | "both";

interface QueuedJob {
  ingest_id: string;
  correlation_id: string;
  status: string;
}

interface JsonRecordsAccepted {
  batch_id: string;
  correlation_id: string;
  record_count: number;
  queued: number;
  index_target: string;
  source_basename: string;
  jobs: QueuedJob[];
}

interface JobStatus {
  ingest_id: string;
  status: string;
  doc_id?: string | null;
  error?: string | null;
  noop?: boolean;
}

const PRESET_DATASET =
  "osint/c2_middle_east_multi_source_1000_v3_en.json";

const TERMINAL = new Set(["succeeded", "failed", "noop"]);
const TRANSIENT = new Set(["poll_error"]);
const POLL_BATCH = 24;
const STATUS_PREVIEW = 40;
const POLL_MS = 2500;

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function normalizeStatus(raw: JobStatus): JobStatus {
  let status = String(raw.status || "").toLowerCase();
  // Some workers mark idempotent hits with noop=true while status stays
  // "succeeded"; treat both as terminal for the progress bar.
  if (raw.noop && status !== "failed") {
    status = "noop";
  }
  return { ...raw, status };
}

function isTerminal(status: string): boolean {
  return TERMINAL.has(status);
}

function isTransient(status: string): boolean {
  return TRANSIENT.has(status) || status.startsWith("http_");
}

/** Prefer a known terminal status over a transient poll failure. */
function mergeStatus(prev: JobStatus | undefined, next: JobStatus): JobStatus {
  const normalized = normalizeStatus(next);
  if (
    prev &&
    isTerminal(prev.status) &&
    isTransient(normalized.status)
  ) {
    return prev;
  }
  return normalized;
}

async function fetchStatusesInBatches(
  jobs: QueuedJob[],
): Promise<JobStatus[]> {
  const next: JobStatus[] = [];
  for (let i = 0; i < jobs.length; i += POLL_BATCH) {
    const slice = jobs.slice(i, i + POLL_BATCH);
    const batch = await Promise.all(
      slice.map(async (job) => {
        try {
          const res = await apiFetch(
            `/api/ingest/ingest/status/${encodeURIComponent(job.ingest_id)}`,
            { cache: "no-store" },
          );
          if (!res.ok) {
            return {
              ingest_id: job.ingest_id,
              status: `http_${res.status}`,
            } satisfies JobStatus;
          }
          return normalizeStatus((await res.json()) as JobStatus);
        } catch {
          return {
            ingest_id: job.ingest_id,
            status: "poll_error",
          } satisfies JobStatus;
        }
      }),
    );
    next.push(...batch);
  }
  return next;
}

export function GlobalIngestPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [usePreset, setUsePreset] = useState(true);
  const indexTarget: IndexTarget = "global";
  const [limit, setLimit] = useState<string>("20");
  const [offset, setOffset] = useState<string>("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<JsonRecordsAccepted | null>(null);
  const [statuses, setStatuses] = useState<JobStatus[]>([]);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const statusesRef = useRef<JobStatus[]>([]);
  const pollingRef = useRef(false);

  statusesRef.current = statuses;

  const progress = useMemo(() => {
    const total = Math.max(
      accepted?.queued ?? 0,
      accepted?.jobs?.length ?? 0,
      statuses.length,
    );
    if (!total) {
      return {
        total: 0,
        done: 0,
        succeeded: 0,
        failed: 0,
        running: 0,
        pending: 0,
        percent: 0,
        complete: false,
      };
    }
    const succeeded = statuses.filter((s) => s.status === "succeeded").length;
    const failed = statuses.filter((s) => s.status === "failed").length;
    const noop = statuses.filter((s) => s.status === "noop").length;
    const done = statuses.filter((s) => isTerminal(s.status)).length;
    const stillOpen = Math.max(0, total - done);
    const runningOnly = statuses.filter((s) => s.status === "running").length;
    const pendingOnly = Math.max(0, stillOpen - runningOnly);
    const percent =
      total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
    // Complete once every queued job has a terminal status (ignore length
    // mismatches from a partial first paint).
    const tracked = accepted?.jobs?.length
      ? accepted.jobs.every((job) => {
          const s = statuses.find((x) => x.ingest_id === job.ingest_id);
          return s != null && isTerminal(s.status);
        })
      : done >= total && total > 0;
    return {
      total,
      done,
      succeeded: succeeded + noop,
      failed,
      running: runningOnly,
      pending: pendingOnly,
      percent: tracked ? 100 : percent,
      complete: tracked,
    };
  }, [accepted, statuses]);

  const elapsedSec =
    startedAt != null ? Math.max(0, (now - startedAt) / 1000) : 0;
  const etaSec = useMemo(() => {
    if (!startedAt || progress.done <= 0 || progress.complete) return null;
    const rate = progress.done / elapsedSec;
    if (!(rate > 0)) return null;
    return (progress.total - progress.done) / rate;
  }, [startedAt, progress, elapsedSec]);

  const pollOpenJobs = useCallback(async (jobs: QueuedJob[]) => {
    if (pollingRef.current) return;
    pollingRef.current = true;
    try {
      const prevById = new Map(
        statusesRef.current.map((s) => [s.ingest_id, s]),
      );
      const open = jobs.filter((job) => {
        const prev = prevById.get(job.ingest_id);
        return !prev || !isTerminal(prev.status);
      });
      // Keep polling until every job is terminal — even if open is empty
      // after a merge glitch, re-check nothing.
      if (open.length === 0) {
        // Ensure statuses cover every accepted job (seed missing as pending).
        if (statusesRef.current.length < jobs.length) {
          setStatuses(
            jobs.map((job) => {
              const prev = prevById.get(job.ingest_id);
              return (
                prev ?? {
                  ingest_id: job.ingest_id,
                  status: "pending",
                }
              );
            }),
          );
        }
        return;
      }
      const fresh = await fetchStatusesInBatches(open);
      const freshById = new Map(fresh.map((s) => [s.ingest_id, s]));
      setStatuses(
        jobs.map((job) => {
          const prev = prevById.get(job.ingest_id);
          const next = freshById.get(job.ingest_id);
          if (next) return mergeStatus(prev, next);
          return (
            prev ?? {
              ingest_id: job.ingest_id,
              status: "pending",
            }
          );
        }),
      );
    } finally {
      pollingRef.current = false;
    }
  }, []);

  useEffect(() => {
    if (!accepted?.jobs?.length || progress.complete) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      await pollOpenJobs(accepted.jobs);
    };
    void tick();
    const timer = window.setInterval(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [accepted, pollOpenJobs, progress.complete]);

  useEffect(() => {
    if (!startedAt || progress.complete) return;
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, [startedAt, progress.complete]);

  useEffect(() => {
    if (progress.complete) setNow(Date.now());
  }, [progress.complete]);

  async function startIngest() {
    setBusy(true);
    setError(null);
    setAccepted(null);
    setStatuses([]);
    setStartedAt(null);
    try {
      const limitN = limit.trim() ? Number(limit) : undefined;
      const offsetN = offset.trim() ? Number(offset) : 0;
      if (limitN !== undefined && (!Number.isFinite(limitN) || limitN < 1)) {
        throw new Error("Limit must be a positive number");
      }
      if (!Number.isFinite(offsetN) || offsetN < 0) {
        throw new Error("Offset must be >= 0");
      }

      const options = {
        split_records: true,
        index_target: indexTarget,
        offset: offsetN,
        limit: limitN ?? null,
        dataset_path: usePreset && !file ? PRESET_DATASET : null,
        filename: file?.name ?? undefined,
      };

      let response: Response;
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("options", JSON.stringify(options));
        response = await apiFetch("/api/ingest/ingest/json-records", {
          method: "POST",
          body: form,
        });
      } else if (usePreset) {
        response = await apiFetch("/api/ingest/ingest/json-records", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(options),
        });
      } else {
        throw new Error("Choose the preset dataset or upload a JSON file");
      }

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(
          `Ingest failed (${response.status}): ${detail.slice(0, 400)}`,
        );
      }
      const body = (await response.json()) as JsonRecordsAccepted;
      setAccepted(body);
      setStatuses(
        (body.jobs ?? []).map((job) => ({
          ingest_id: job.ingest_id,
          status: String(job.status || "pending").toLowerCase(),
        })),
      );
      setStartedAt(Date.now());
      setNow(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingest failed");
    } finally {
      setBusy(false);
    }
  }

  const previewStatuses = statuses.slice(0, STATUS_PREVIEW);

  return (
    <section className="mx-auto w-full max-w-5xl rounded-md border bg-card p-4">
      <h2 className="text-lg font-semibold">Global corpus ingest</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Split a JSON record corpus into one Markdown document per record
        (<code className="text-xs">filename/doc_id</code> source), run the NLP
        pipeline, and index dense + sparse passages. Structured fields (not
        title/text) are stored as ontology concepts.
      </p>

      <div className="mt-4 space-y-3 text-sm">
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={usePreset}
            onChange={(e) => {
              setUsePreset(e.target.checked);
              if (e.target.checked) setFile(null);
            }}
          />
          <span>
            Use preset{" "}
            <code className="text-xs break-all">{PRESET_DATASET}</code>
            {" "}(server-side under <code className="text-xs">datasets/</code>)
          </span>
        </label>

        <div>
          <label className="mb-1 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Or upload JSON
          </label>
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(e) => {
              const next = e.target.files?.[0] ?? null;
              setFile(next);
              if (next) setUsePreset(false);
            }}
            className="block w-full text-sm"
          />
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Offset
            </span>
            <input
              type="number"
              min={0}
              value={offset}
              disabled={busy}
              onChange={(e) => setOffset(e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Limit
            </span>
            <input
              type="number"
              min={1}
              value={limit}
              disabled={busy}
              placeholder="all"
              onChange={(e) => setLimit(e.target.value)}
              className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
            />
          </label>
        </div>
        <p className="text-xs text-muted-foreground">
          Indexes into the shared Vespa <strong>global</strong> catalog (visible
          to all users). Personal files belong under My files → user streaming
          index.
        </p>

        <button
          type="button"
          disabled={busy || (!usePreset && !file)}
          onClick={() => void startIngest()}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {busy ? "Queueing…" : "Start global ingest"}
        </button>
      </div>

      {error ? (
        <p className="mt-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}

      {accepted ? (
        <div className="mt-4 space-y-3 text-sm">
          <p>
            Queued <strong>{accepted.queued}</strong> / {accepted.record_count}{" "}
            records as batch{" "}
            <code className="text-xs">{accepted.batch_id}</code> →{" "}
            <strong>{accepted.index_target}</strong> (
            <code className="text-xs">{accepted.source_basename}/…</code>)
          </p>

          <div className="rounded-md border bg-muted/30 p-3">
            <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium">
                {progress.complete
                  ? "Batch complete"
                  : "Ingest in progress"}
              </span>
              <span className="text-xs text-muted-foreground">
                {progress.done} / {progress.total} jobs ({progress.percent}%)
              </span>
            </div>
            <div
              className="h-2.5 w-full overflow-hidden rounded-full bg-secondary"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress.percent}
              aria-label="Ingest progress"
            >
              <div
                className={`h-full min-w-0 rounded-full transition-[width] duration-500 ${
                  progress.failed > 0 && progress.complete
                    ? "bg-amber-500"
                    : progress.complete
                      ? "bg-emerald-500"
                      : "bg-primary"
                }`}
                style={{ width: `${progress.percent}%` }}
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>
                {progress.succeeded} ok · {progress.failed} failed ·{" "}
                {progress.running} running · {progress.pending} pending
              </span>
              <span>Elapsed {formatDuration(elapsedSec)}</span>
              <span>
                {progress.complete
                  ? "ETA —"
                  : etaSec == null
                    ? "ETA estimating…"
                    : `ETA ~${formatDuration(etaSec)}`}
              </span>
            </div>
          </div>

          <ul className="max-h-48 overflow-auto rounded border text-xs">
            {previewStatuses.map((s) => (
              <li
                key={s.ingest_id}
                className="flex justify-between gap-2 border-b px-2 py-1 last:border-0"
              >
                <span className="font-mono truncate">{s.ingest_id}</span>
                <span
                  className={
                    s.status === "failed"
                      ? "text-destructive"
                      : s.status === "succeeded" || s.status === "noop"
                        ? "text-emerald-500"
                        : "text-muted-foreground"
                  }
                >
                  {s.status}
                  {s.error ? `: ${s.error.slice(0, 80)}` : ""}
                </span>
              </li>
            ))}
          </ul>
          {statuses.length > STATUS_PREVIEW ? (
            <p className="text-xs text-muted-foreground">
              Showing first {STATUS_PREVIEW} of {statuses.length} jobs (progress
              counts all).
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
