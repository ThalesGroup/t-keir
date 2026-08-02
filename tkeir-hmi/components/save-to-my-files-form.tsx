"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Folder,
  FolderPlus,
  Loader2,
  Save,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/src/auth/useApiClient";
import { cn } from "@/lib/utils";

type WorkspaceEntry = {
  name: string;
  path: string;
  kind: "file" | "directory";
};

type TreeResponse = {
  user_space?: string;
  path: string;
  entries: WorkspaceEntry[];
};

export type SaveToMyFilesFormProps = {
  open: boolean;
  title?: string;
  /** Initial directory under the user workspace (e.g. ``wiki``). */
  defaultDirectory?: string;
  /** Filename only (``.md`` appended if missing). */
  defaultFilename: string;
  busy?: boolean;
  onCancel: () => void;
  /** Called with workspace-relative path like ``wiki/mt_red_sea_eagle.md``. */
  onConfirm: (path: string) => void | Promise<void>;
};

async function readError(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string };
    if (body.detail) return body.detail;
  } catch {
    /* ignore */
  }
  return `Request failed (${res.status})`;
}

function normalizeFilename(raw: string): string {
  let name = raw.trim().replace(/^\/+/, "");
  if (!name) name = "wiki.md";
  if (name.includes("/")) {
    name = name.split("/").pop() || "wiki.md";
  }
  if (!name.toLowerCase().endsWith(".md")) {
    name = `${name}.md`;
  }
  return name;
}

/**
 * Compact My-files destination picker: browse/create folders + filename.
 */
export function SaveToMyFilesForm({
  open,
  title = "Save to My files",
  defaultDirectory = "wiki",
  defaultFilename,
  busy = false,
  onCancel,
  onConfirm,
}: SaveToMyFilesFormProps) {
  const [cwd, setCwd] = useState(defaultDirectory.replace(/^\/+|\/+$/g, ""));
  const [tree, setTree] = useState<TreeResponse | null>(null);
  const [filename, setFilename] = useState(defaultFilename);
  const [newFolder, setNewFolder] = useState("");
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setCwd(defaultDirectory.replace(/^\/+|\/+$/g, ""));
    setFilename(defaultFilename);
    setNewFolder("");
    setLocalError(null);
  }, [open, defaultDirectory, defaultFilename]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLocalError(null);
    try {
      const qs = cwd ? `?path=${encodeURIComponent(cwd)}` : "";
      const res = await apiFetch(`/api/ingest/workspace/tree${qs}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        // Missing folder (e.g. default ``wiki/``) — offer create, list root.
        if (cwd && (res.status === 404 || res.status === 400)) {
          setLocalError(
            `Folder “${cwd}” is not in My files yet — create it below or pick another directory.`,
          );
          setTree({ path: cwd, entries: [] });
          return;
        }
        throw new Error(await readError(res));
      }
      setTree((await res.json()) as TreeResponse);
    } catch (err) {
      setTree(null);
      setLocalError(
        err instanceof Error ? err.message : "Failed to list My files",
      );
    } finally {
      setLoading(false);
    }
  }, [cwd]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  const directories = useMemo(
    () => (tree?.entries ?? []).filter((entry) => entry.kind === "directory"),
    [tree],
  );

  const crumbs = cwd ? cwd.split("/") : [];
  const fullPath = cwd
    ? `${cwd}/${normalizeFilename(filename)}`
    : normalizeFilename(filename);

  async function createFolder() {
    const name = newFolder.trim().replace(/[\\/]+/g, "");
    if (!name) return;
    const path = cwd ? `${cwd}/${name}` : name;
    setLoading(true);
    setLocalError(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/mkdir", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) throw new Error(await readError(res));
      setNewFolder("");
      setCwd(path);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "mkdir failed");
      setLoading(false);
    }
  }

  async function ensureCurrentFolder() {
    if (!cwd) return;
    setLoading(true);
    setLocalError(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/mkdir", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path: cwd }),
      });
      if (!res.ok) throw new Error(await readError(res));
      await refresh();
    } catch (err) {
      setLocalError(
        err instanceof Error ? err.message : "Could not create folder",
      );
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">
            Choose a folder under My files, optionally create one, and set the
            filename.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={busy}
          onClick={onCancel}
          aria-label="Close save form"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-1 text-xs">
        <button
          type="button"
          className={cn(
            "rounded px-1.5 py-0.5 hover:bg-muted",
            !cwd && "font-semibold text-primary",
          )}
          disabled={busy || loading}
          onClick={() => setCwd("")}
        >
          My files
        </button>
        {crumbs.map((part, index) => {
          const path = crumbs.slice(0, index + 1).join("/");
          return (
            <span key={path} className="flex items-center gap-1">
              <span className="text-muted-foreground">/</span>
              <button
                type="button"
                className={cn(
                  "rounded px-1.5 py-0.5 hover:bg-muted",
                  path === cwd && "font-semibold text-primary",
                )}
                disabled={busy || loading}
                onClick={() => setCwd(path)}
              >
                {part}
              </button>
            </span>
          );
        })}
      </div>

      <div className="max-h-40 overflow-y-auto rounded-md border bg-background">
        {loading && !tree ? (
          <p className="flex items-center gap-2 px-3 py-4 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading folders…
          </p>
        ) : directories.length === 0 ? (
          <p className="px-3 py-4 text-sm text-muted-foreground">
            No subfolders here. Create one below or save in this directory.
          </p>
        ) : (
          <ul className="divide-y">
            {directories.map((entry) => (
              <li key={entry.path}>
                <button
                  type="button"
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted/60"
                  disabled={busy || loading}
                  onClick={() => setCwd(entry.path)}
                >
                  <Folder className="h-4 w-4 text-amber-600" />
                  {entry.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Input
          value={newFolder}
          onChange={(event) => setNewFolder(event.target.value)}
          placeholder="New folder name"
          disabled={busy || loading}
          className="max-w-xs"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || loading || !newFolder.trim()}
          onClick={() => void createFolder()}
        >
          <FolderPlus className="h-4 w-4" />
          Create folder
        </Button>
        {cwd ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy || loading}
            onClick={() => void ensureCurrentFolder()}
          >
            <Folder className="h-4 w-4" />
            Create “{cwd.split("/").pop()}” here
          </Button>
        ) : null}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-medium text-muted-foreground">
          Filename
        </label>
        <Input
          value={filename}
          onChange={(event) => setFilename(event.target.value)}
          placeholder="wiki.md"
          disabled={busy}
        />
      </div>

      <p className="font-mono text-xs text-muted-foreground">
        Will save as: <span className="text-foreground">{fullPath}</span>
      </p>

      {localError ? (
        <p className="text-sm text-destructive">{localError}</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          disabled={busy || loading || !normalizeFilename(filename)}
          onClick={() => void onConfirm(fullPath)}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save to My files
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
