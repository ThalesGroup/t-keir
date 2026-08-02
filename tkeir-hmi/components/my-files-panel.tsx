"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Eye,
  FilePlus2,
  Folder,
  FolderPlus,
  Loader2,
  RefreshCw,
  Send,
  Trash2,
  Upload,
  Database,
  ShoppingBasket,
  X,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MarkdownContent } from "@/components/markdown-content";
import {
  MyFilesBasketBrief,
  type BasketIndexOptions,
  type BasketItem,
} from "@/components/my-files-basket-brief";
import { useAuth } from "@/src/auth/AuthProvider";
import { apiFetch } from "@/src/auth/useApiClient";
import { cn } from "@/lib/utils";

type WorkspaceEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
  size_bytes?: number;
  status?: string;
  source_ref?: string | null;
  ingest_id?: string | null;
  passage_count?: number;
  updated_at?: string | null;
  copied_from_user?: string | null;
  copied_from_path?: string | null;
};

type TreeResponse = {
  user_space: string;
  path: string;
  entries: WorkspaceEntry[];
};

type FilePreview = {
  path: string;
  name: string;
  content: string;
  content_type?: string;
};

type IndexProgress = {
  paths: string[];
  total: number;
  done: number;
  failed: number;
  active: boolean;
};

const SHARE_ROLES = ["c2-j2-analyst", "c2-moc-watch", "c2-j2x-humint"];
const INDEX_POLL_MS = 2000;

function isMarkdownPath(path: string): boolean {
  const lower = path.toLowerCase();
  return lower.endsWith(".md") || lower.endsWith(".markdown");
}

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (body.detail) return body.detail;
  } catch {
    // ignore
  }
  return `Request failed (${res.status})`;
}

export function MyFilesPanel() {
  const { authEnabled, roles, runtimeConfig, activePersonaId } = useAuth();
  const isCommander =
    activePersonaId === "commander" || roles.includes("c2-ctf-commander");
  const [cwd, setCwd] = useState(isCommander ? "received" : "");
  const [tree, setTree] = useState<TreeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newFolder, setNewFolder] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [preview, setPreview] = useState<FilePreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [indexProgress, setIndexProgress] = useState<IndexProgress | null>(
    null,
  );
  const indexPathsRef = useRef<Set<string>>(new Set());
  const [basket, setBasket] = useState<BasketItem[]>([]);

  const canShareToCommander =
    !authEnabled || SHARE_ROLES.some((role) => roles.includes(role));
  // Every authenticated persona can index into their personal Vespa user index.
  const canIndexSelected = true;

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const qs = cwd ? `?path=${encodeURIComponent(cwd)}` : "";
      const res = await apiFetch(`/api/ingest/workspace/tree${qs}`, {
        cache: "no-store",
      });
      if (!res.ok) throw new Error(await readError(res));
      const nextTree = (await res.json()) as TreeResponse;
      setTree(nextTree);
      setSelected(new Set());
      // Refresh basket metadata (status / passages / source_ref) without dropping items.
      setBasket((prev: BasketItem[]) => {
        if (prev.length === 0) return prev;
        const byPath = new Map(
          (nextTree.entries ?? [])
            .filter((e: WorkspaceEntry) => e.kind === "file")
            .map((e: WorkspaceEntry) => [e.path, e]),
        );
        return prev.map((item: BasketItem) => {
          const live = byPath.get(item.path);
          if (!live) return item;
          const space = nextTree.user_space;
          const sourceRef =
            live.source_ref ||
            item.source_ref ||
            (space ? `user:${space}:${live.path}` : item.source_ref);
          return {
            ...item,
            name: live.name || item.name,
            source_ref: sourceRef,
            status: live.status ?? item.status,
            passage_count: live.passage_count ?? item.passage_count,
          };
        });
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to list files");
    } finally {
      setBusy(false);
    }
  }, [cwd]);

  const pollIndexStatus = useCallback(async () => {
    const tracked = Array.from(indexPathsRef.current);
    if (tracked.length === 0) return;
    try {
      const res = await apiFetch("/api/ingest/workspace/status", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ paths: tracked }),
        cache: "no-store",
      });
      if (!res.ok) return;
      const body = (await res.json()) as {
        total?: number;
        done?: number;
        active?: boolean;
        counts?: { indexed?: number; failed?: number; indexing?: number };
        files?: {
          path: string;
          status?: string;
          passage_count?: number;
        }[];
      };
      const total = body.total ?? tracked.length;
      const failed = body.counts?.failed ?? 0;
      const indexed = body.counts?.indexed ?? 0;
      const stillIndexing = Boolean(body.active);
      // When nothing is left indexing, snap the bar to 100% even if a few
      // catalog rows briefly report as "other" — otherwise the UI shows
      // "Indexing complete" with a half-filled bar.
      const done = stillIndexing
        ? (body.done ?? 0)
        : Math.max(body.done ?? 0, total);
      const active = stillIndexing && done < total;
      setIndexProgress({
        paths: tracked,
        total,
        done,
        failed,
        active,
      });
      if (body.files?.length) {
        const byPath = new Map(
          body.files.map((f: { path: string; status?: string; passage_count?: number }) => [
            f.path,
            f,
          ]),
        );
        setBasket((prev: BasketItem[]) =>
          prev.map((item: BasketItem) => {
            const live = byPath.get(item.path);
            if (!live) return item;
            return {
              ...item,
              status: live.status ?? item.status,
              passage_count: live.passage_count ?? item.passage_count,
            };
          }),
        );
      }
      if (!active) {
        indexPathsRef.current = new Set();
        setInfo(
          `Indexing finished: ${indexed} indexed` +
            (failed ? `, ${failed} failed` : "") +
            " in your personal stream index",
        );
        await refresh();
      }
    } catch {
      // Keep polling; transient errors should not clear progress.
    }
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!indexProgress?.active) return;
    void pollIndexStatus();
    const timer = window.setInterval(() => {
      void pollIndexStatus();
    }, INDEX_POLL_MS);
    return () => window.clearInterval(timer);
  }, [indexProgress?.active, pollIndexStatus]);

  function startIndexTracking(paths: string[]) {
    const next = new Set(paths.filter(Boolean));
    if (next.size === 0) return;
    indexPathsRef.current = next;
    setIndexProgress({
      paths: Array.from(next),
      total: next.size,
      done: 0,
      failed: 0,
      active: true,
    });
  }

  const fileEntries = useMemo(
    () =>
      (tree?.entries ?? []).filter(
        (entry: WorkspaceEntry) => entry.kind === "file",
      ),
    [tree],
  );

  function toggleSelected(path: string) {
    setSelected((prev: Set<string>) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function toggleSelectAllFiles() {
    setSelected((prev: Set<string>) => {
      if (fileEntries.length === 0) return prev;
      const allSelected = fileEntries.every((entry: WorkspaceEntry) =>
        prev.has(entry.path),
      );
      if (allSelected) return new Set();
      return new Set(fileEntries.map((entry: WorkspaceEntry) => entry.path));
    });
  }

  async function createFolder() {
    const name = newFolder.trim();
    if (!name) return;
    const path = cwd ? `${cwd}/${name}` : name;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/mkdir", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) throw new Error(await readError(res));
      setNewFolder("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "mkdir failed");
    } finally {
      setBusy(false);
    }
  }

  async function uploadFile(file: File) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const form = new FormData();
      form.append("file", file);
      // Store only — indexing is an explicit "Index selected" action.
      form.append("index", "false");
      if (uploadName.trim()) {
        const rel = cwd ? `${cwd}/${uploadName.trim()}` : uploadName.trim();
        form.append("path", rel);
      } else if (cwd) {
        form.append("directory", cwd);
      }
      const res = await apiFetch("/api/ingest/workspace/upload", {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await readError(res));
      const body = (await res.json()) as {
        split_records?: boolean;
        created_count?: number;
        folder?: string;
        path?: string;
      };
      setUploadName("");
      if (body.split_records) {
        const folder = body.folder || "";
        setInfo(
          `Imported ${body.created_count ?? 0} markdown file(s)` +
            (folder ? ` under ${folder}/` : "") +
            ". Select files and click Index selected to run NLP + personal indexing.",
        );
        if (folder) setCwd(folder);
        else await refresh();
      } else {
        setInfo(
          `Saved ${body.path || file.name}. Select it and click Index selected to index.`,
        );
        await refresh();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function openPreview(entry: WorkspaceEntry) {
    if (entry.kind !== "file" || !isMarkdownPath(entry.path)) return;
    setPreviewBusy(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/ingest/workspace/file?path=${encodeURIComponent(entry.path)}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error(await readError(res));
      const body = (await res.json()) as {
        path: string;
        name: string;
        content: string;
        content_type?: string;
      };
      setPreview({
        path: body.path,
        name: body.name || entry.name,
        content: body.content ?? "",
        content_type: body.content_type,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "preview failed");
    } finally {
      setPreviewBusy(false);
    }
  }

  async function syncFile(path: string) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/sync", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) throw new Error(await readError(res));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "sync failed");
    } finally {
      setBusy(false);
    }
  }

  async function deleteEntry(entry: WorkspaceEntry) {
    const label =
      entry.kind === "directory"
        ? `Delete folder “${entry.name}” and its contents?`
        : `Delete “${entry.name}” and remove it from your Vespa user index?`;
    if (!window.confirm(label)) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch(
        `/api/ingest/workspace/file?path=${encodeURIComponent(entry.path)}`,
        { method: "DELETE" },
      );
      if (!res.ok) throw new Error(await readError(res));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "delete failed");
    } finally {
      setBusy(false);
    }
  }

  async function sendSelectedToCommander() {
    const paths = Array.from(selected);
    if (paths.length === 0) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/copy-to", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          paths,
          target_user_space: "commander",
        }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const body = (await res.json()) as {
        copied_count?: number;
        dest_prefix?: string;
        errors?: { path: string; error: string }[];
      };
      const errCount = body.errors?.length ?? 0;
      setInfo(
        `Sent ${body.copied_count ?? 0} file(s) to commander My files` +
          (body.dest_prefix
            ? ` under ${body.dest_prefix}/ (Received documents)`
            : " (Received documents)") +
          (errCount ? ` (${errCount} failed)` : ""),
      );
      setSelected(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "share failed");
    } finally {
      setBusy(false);
    }
  }

  async function indexSelected() {
    const paths = Array.from(selected);
    if (paths.length === 0) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const boDataset =
        runtimeConfig?.businessOntologyDataset?.trim() || "osint";
      const res = await apiFetch("/api/ingest/workspace/index", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          paths,
          business_ontology_dataset: boDataset,
        }),
      });
      if (!res.ok) throw new Error(await readError(res));
      const body = (await res.json()) as {
        queued_count?: number;
        queued?: { path?: string }[];
        errors?: { path: string; error: string }[];
        business_ontology_dataset?: string;
      };
      const errCount = body.errors?.length ?? 0;
      const queuedPaths = (body.queued ?? [])
        .map((item: { path?: string }) => item.path)
        .filter((path): path is string => Boolean(path));
      setInfo(
        `Queued ${body.queued_count ?? 0} file(s) for NLP + user index` +
          ` (business ontology: ${body.business_ontology_dataset || boDataset})` +
          (errCount ? ` (${errCount} failed)` : ""),
      );
      if (queuedPaths.length > 0) {
        startIndexTracking(queuedPaths);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "index failed");
    } finally {
      setBusy(false);
    }
  }

  function entryToBasketItem(entry: WorkspaceEntry): BasketItem | null {
    if (entry.kind !== "file") return null;
    const space = tree?.user_space;
    const sourceRef =
      entry.source_ref ||
      (space ? `user:${space}:${entry.path}` : "");
    if (!sourceRef) return null;
    return {
      path: entry.path,
      name: entry.name,
      source_ref: sourceRef,
      status: entry.status,
      passage_count: entry.passage_count,
    };
  }

  function addSelectedToBasket() {
    const byPath = new Map(
      fileEntries.map((e: WorkspaceEntry) => [e.path, e]),
    );
    setBasket((prev: BasketItem[]) => {
      const next = new Map(prev.map((item: BasketItem) => [item.path, item]));
      for (const path of selected) {
        const entry = byPath.get(path);
        if (!entry) continue;
        const item = entryToBasketItem(entry);
        if (item) next.set(path, item);
      }
      return Array.from(next.values());
    });
    setInfo(`Added ${selected.size} file(s) to the brief basket`);
  }

  function addEntryToBasket(entry: WorkspaceEntry) {
    const item = entryToBasketItem(entry);
    if (!item) return;
    setBasket((prev: BasketItem[]) => {
      if (prev.some((b: BasketItem) => b.path === item.path)) return prev;
      return [...prev, item];
    });
  }

  async function indexBasketPaths(
    paths: string[],
    options?: BasketIndexOptions,
  ) {
    if (paths.length === 0) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const boDataset =
        options?.business_ontology_dataset?.trim() ||
        runtimeConfig?.businessOntologyDataset?.trim() ||
        "osint";
      const body: Record<string, unknown> = {
        paths,
        business_ontology_dataset: boDataset,
      };
      if (options?.business_ontology) {
        body.business_ontology = options.business_ontology;
      }
      const res = await apiFetch("/api/ingest/workspace/index", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(await readError(res));
      const payload = (await res.json()) as {
        queued_count?: number;
        queued?: { path?: string }[];
        errors?: { path: string; error: string }[];
      };
      const queuedPaths = (payload.queued ?? [])
        .map((item: { path?: string }) => item.path)
        .filter((path): path is string => Boolean(path));
      setInfo(
        `Queued ${payload.queued_count ?? 0} basket file(s) for NLP + user index` +
          (options?.business_ontology
            ? " (with uploaded business ontology)"
            : ` (dataset ${boDataset})`),
      );
      if (queuedPaths.length > 0) {
        startIndexTracking(queuedPaths);
      }
      // Mark basket items as indexing until poll refresh.
      setBasket((prev: BasketItem[]) =>
        prev.map((item: BasketItem) =>
          paths.includes(item.path)
            ? {
                ...item,
                status:
                  item.status === "indexed" ? item.status : "indexing",
              }
            : item,
        ),
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "index failed");
    } finally {
      setBusy(false);
    }
  }

  const crumbs = cwd ? cwd.split("/") : [];
  const selectedCount = selected.size;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">
          Personal corpus
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">My files</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Import documents into your private workspace (stored only — not
          indexed yet). Select files and use Index selected to run the NLP
          pipeline with the configured business ontology (
          <code>
            {runtimeConfig?.businessOntologyDataset?.trim() || "osint"}
          </code>
          ) into your Vespa user streaming group. Add indexed files to the
          basket to generate a RAG brief and explore the merged ontology.
          Markdown is viewable in-place. Record-oriented JSON corpora are
          split into one <code>{"{doc_id}.md"}</code> file per record.
          Analyst, HUMINT, and Watch can send selected files to the commander{" "}
          <code>received/</code> folder.
        </p>
        {isCommander ? (
          <Alert className="mt-3">
            <Folder className="h-4 w-4" />
            <AlertTitle>Received documents</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-2">
              Shared reports and files from other personas land under{" "}
              <code>received/&lt;sender&gt;/</code>.
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => setCwd("received")}
              >
                Open received
              </Button>
            </AlertDescription>
          </Alert>
        ) : null}
        {tree?.user_space && (
          <p className="mt-1 text-xs text-muted-foreground">
            user_space: <code>{tree.user_space}</code>
          </p>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Workspace error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {info && (
        <Alert>
          <Send className="h-4 w-4" />
          <AlertTitle>Workspace</AlertTitle>
          <AlertDescription>{info}</AlertDescription>
        </Alert>
      )}

      {indexProgress && (indexProgress.active || indexProgress.done > 0) && (
        <div className="rounded-lg border px-4 py-3">
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">
              {indexProgress.active
                ? "Indexing personal stream…"
                : "Indexing complete"}
            </span>
            <span className="text-muted-foreground">
              {Math.min(indexProgress.done, indexProgress.total)} /{" "}
              {indexProgress.total}
              {indexProgress.failed > 0
                ? ` (${indexProgress.failed} failed)`
                : ""}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-[width] duration-300",
                indexProgress.failed > 0 && !indexProgress.active
                  ? "bg-amber-500"
                  : "bg-primary",
              )}
              style={{
                width: `${
                  indexProgress.total > 0
                    ? Math.min(
                        100,
                        (indexProgress.done / indexProgress.total) * 100,
                      )
                    : 0
                }%`,
              }}
            />
          </div>
          {indexProgress.active && (
            <p className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Updating catalog and Vespa user streaming group
            </p>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <button
          type="button"
          className="rounded px-1.5 py-0.5 hover:bg-muted"
          onClick={() => setCwd("")}
        >
          files
        </button>
        {crumbs.map((part, index) => {
          const path = crumbs.slice(0, index + 1).join("/");
          return (
            <span key={path} className="flex items-center gap-2">
              <span className="text-muted-foreground">/</span>
              <button
                type="button"
                className="rounded px-1.5 py-0.5 hover:bg-muted"
                onClick={() => setCwd(path)}
              >
                {part}
              </button>
            </span>
          );
        })}
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="ml-auto"
          disabled={busy}
          onClick={() => void refresh()}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 rounded-lg border p-4 sm:grid-cols-2">
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">
            New folder
          </label>
          <div className="flex gap-2">
            <Input
              value={newFolder}
              onChange={(event) => setNewFolder(event.target.value)}
              placeholder="assessments"
            />
            <Button
              type="button"
              size="sm"
              disabled={busy || !newFolder.trim()}
              onClick={() => void createFolder()}
            >
              <FolderPlus className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-medium text-muted-foreground">
            Import file (optional rename)
          </label>
          <div className="flex gap-2">
            <Input
              value={uploadName}
              onChange={(event) => setUploadName(event.target.value)}
              placeholder="entity_track.md"
            />
            <label
              className={cn(
                "inline-flex h-9 cursor-pointer items-center gap-1 rounded-md border px-3 text-sm",
                busy && "pointer-events-none opacity-50",
              )}
            >
              <Upload className="h-4 w-4" />
              File
              <input
                type="file"
                className="hidden"
                disabled={busy}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) void uploadFile(file);
                  event.currentTarget.value = "";
                }}
              />
            </label>
          </div>
        </div>
      </div>

      {(canShareToCommander || canIndexSelected) && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2">
          <Button
            type="button"
            size="sm"
            variant="ghost"
            disabled={busy || fileEntries.length === 0}
            onClick={toggleSelectAllFiles}
          >
            {fileEntries.length > 0 &&
            fileEntries.every((entry: WorkspaceEntry) =>
              selected.has(entry.path),
            )
              ? "Clear selection"
              : "Select all files"}
          </Button>
          <span className="text-xs text-muted-foreground">
            {selectedCount} selected
          </span>
          {canShareToCommander && (
            <Button
              type="button"
              size="sm"
              disabled={busy || selectedCount === 0}
              onClick={() => void sendSelectedToCommander()}
            >
              <Send className="h-4 w-4" />
              Send selected to commander
            </Button>
          )}
          {canIndexSelected && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={busy || selectedCount === 0}
              onClick={() => void indexSelected()}
            >
              <Database className="h-4 w-4" />
              Index selected
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || selectedCount === 0}
            onClick={addSelectedToBasket}
          >
            <ShoppingBasket className="h-4 w-4" />
            Add to basket
            {basket.length > 0 ? ` (${basket.length})` : ""}
          </Button>
        </div>
      )}

      <MyFilesBasketBrief
        items={basket}
        indexing={Boolean(indexProgress?.active) || busy}
        onRemove={(path) =>
          setBasket((prev: BasketItem[]) =>
            prev.filter((item: BasketItem) => item.path !== path),
          )
        }
        onClear={() => setBasket([])}
        onIndexMissing={indexBasketPaths}
      />

      <div className="overflow-hidden rounded-lg border">
        {(tree?.entries ?? []).length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center text-sm text-muted-foreground">
            <FilePlus2 className="h-8 w-8 opacity-50" />
            <p>No files here yet. Create a folder or import a document.</p>
          </div>
        ) : (
          <ul className="divide-y">
            {(tree?.entries ?? []).map((entry: WorkspaceEntry) => (
              <li
                key={entry.path}
                className="flex items-center gap-3 px-3 py-2.5 text-sm"
              >
                {entry.kind === "file" ? (
                  <input
                    type="checkbox"
                    className="h-4 w-4 shrink-0"
                    checked={selected.has(entry.path)}
                    disabled={busy}
                    aria-label={`Select ${entry.name}`}
                    onChange={() => toggleSelected(entry.path)}
                  />
                ) : (
                  <span className="inline-block w-4 shrink-0" />
                )}
                {entry.kind === "directory" ? (
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 truncate text-left font-medium hover:underline"
                    onClick={() => setCwd(entry.path)}
                  >
                    <Folder
                      className={cn(
                        "h-4 w-4 shrink-0 text-muted-foreground",
                        entry.path === "received" && "text-primary",
                      )}
                    />
                    <span className="truncate">
                      {entry.path === "received"
                        ? "received (Received documents)"
                        : entry.name}
                    </span>
                  </button>
                ) : (
                  <div className="min-w-0 flex-1">
                    {isMarkdownPath(entry.path) ? (
                      <button
                        type="button"
                        className="truncate text-left font-medium hover:underline"
                        disabled={busy || previewBusy}
                        onClick={() => void openPreview(entry)}
                        title="View markdown"
                      >
                        {entry.name}
                      </button>
                    ) : (
                      <div className="truncate font-medium">{entry.name}</div>
                    )}
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {entry.status && (
                        <Badge
                          variant="outline"
                          className={cn(
                            entry.status === "indexed" &&
                              "border-emerald-500/40 text-emerald-700 dark:text-emerald-400",
                            entry.status === "indexing" &&
                              "border-amber-500/40 text-amber-700 dark:text-amber-400",
                            entry.status === "failed" &&
                              "border-destructive/40 text-destructive",
                          )}
                        >
                          {entry.status}
                        </Badge>
                      )}
                      {entry.copied_from_user ? (
                        <Badge variant="outline">
                          from {entry.copied_from_user}
                        </Badge>
                      ) : null}
                      {typeof entry.passage_count === "number" &&
                        entry.passage_count > 0 && (
                          <span>{entry.passage_count} passage(s)</span>
                        )}
                      {typeof entry.size_bytes === "number" && (
                        <span>{entry.size_bytes} B</span>
                      )}
                      {entry.copied_from_user && (
                        <span>
                          from {entry.copied_from_user}
                          {entry.copied_from_path
                            ? `:${entry.copied_from_path}`
                            : ""}
                        </span>
                      )}
                    </div>
                  </div>
                )}
                <div className="flex shrink-0 gap-1">
                  {entry.kind === "file" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      title="Add to brief basket"
                      onClick={() => addEntryToBasket(entry)}
                    >
                      <ShoppingBasket
                        className={cn(
                          "h-4 w-4",
                          basket.some((b: BasketItem) => b.path === entry.path) &&
                            "text-primary",
                        )}
                      />
                    </Button>
                  )}
                  {entry.kind === "file" && isMarkdownPath(entry.path) && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy || previewBusy}
                      title="View markdown"
                      onClick={() => void openPreview(entry)}
                    >
                      {previewBusy ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Eye className="h-4 w-4" />
                      )}
                    </Button>
                  )}
                  {entry.kind === "file" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busy}
                      title="Sync index status"
                      onClick={() => void syncFile(entry.path)}
                    >
                      <RefreshCw className="h-4 w-4" />
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    title="Delete"
                    onClick={() => void deleteEntry(entry)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {preview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border bg-background shadow-lg">
            <div className="flex items-center gap-2 border-b px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{preview.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {preview.path}
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setPreview(null)}
                title="Close"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="overflow-y-auto px-4 py-4">
              <MarkdownContent content={preview.content} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
