"use client";

import { useCallback, useEffect, useState } from "react";

import { MarkdownContent } from "@/components/markdown-content";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { LLM_WIKI_WORKFLOW } from "@/lib/persona-workflows";
import { apiFetch } from "@/src/auth/useApiClient";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type OkfBundle = {
  bundle_id: string;
  user_space: string;
  query?: string | null;
  concept_count: number;
  created_at?: string;
  path?: string;
};

type BundleDetail = {
  bundle_id: string;
  index_md?: string;
  concepts?: string[];
  bundle?: OkfBundle;
  wiki_md?: string;
  has_wiki?: boolean;
};

type AgentRunPayload = {
  run?: {
    status?: string;
    error?: string | null;
    params?: Record<string, unknown>;
  };
  steps?: Array<{
    step_index: number;
    status: string;
    thought_excerpt?: string;
  }>;
  blackboard?: Array<{
    kind?: string;
    builtin?: string;
    bundle_id?: string;
  }>;
};

function errorDetail(body: {
  detail?: string | { detail?: string };
}): string | undefined {
  if (typeof body.detail === "string") {
    return body.detail;
  }
  if (body.detail && typeof body.detail === "object") {
    return body.detail.detail;
  }
  return undefined;
}

function bundleIdFromRun(payload: AgentRunPayload): string | null {
  const fromParams = payload.run?.params?.bundle_id;
  if (typeof fromParams === "string" && fromParams.trim()) {
    return fromParams.trim();
  }
  for (const entry of payload.blackboard ?? []) {
    if (
      entry.kind === "builtin" &&
      entry.builtin === "okf_scoped_export" &&
      typeof entry.bundle_id === "string" &&
      entry.bundle_id.trim()
    ) {
      return entry.bundle_id.trim();
    }
  }
  return null;
}

const TERMINAL_STATUSES = new Set([
  "succeeded",
  "failed",
  "blocked",
  "killed",
  "cancelled",
]);


/** OKF-backed LLMWiki workspace: generate, edit, and publish wiki pages. */
export function LlmWikiPanel() {
  const [bundles, setBundles] = useState<OkfBundle[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<BundleDetail | null>(null);
  const [conceptId, setConceptId] = useState<string | null>(null);
  const [conceptMd, setConceptMd] = useState<string>("");
  const [query, setQuery] = useState("Objective ALPHA");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wikiDraft, setWikiDraft] = useState("");
  const [wikiSaved, setWikiSaved] = useState("");
  const [wikiMode, setWikiMode] = useState<"edit" | "preview">("edit");
  const [activeTab, setActiveTab] = useState("index");
  const [runId, setRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [runSteps, setRunSteps] = useState<number>(0);
  const [workflowBound, setWorkflowBound] = useState<boolean | null>(null);
  const [boundWorkflow, setBoundWorkflow] = useState(LLM_WIKI_WORKFLOW);

  const refreshList = useCallback(async () => {
    const res = await apiFetch("/api/okf/okf/bundles", { cache: "no-store" });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const body = (await res.json()) as { bundles?: OkfBundle[] };
    setBundles(body.bundles ?? []);
  }, []);

  const refreshWorkflowBinding = useCallback(async (): Promise<boolean> => {
    try {
      const res = await apiFetch("/api/agent/agent/workflows", {
        cache: "no-store",
      });
      if (!res.ok) {
        setWorkflowBound(false);
        return false;
      }
      const body = (await res.json()) as { workflows?: string[] };
      const names = body.workflows ?? [];
      const hasLlmWiki = names.includes(LLM_WIKI_WORKFLOW);
      setBoundWorkflow(LLM_WIKI_WORKFLOW);
      setWorkflowBound(hasLlmWiki);
      return hasLlmWiki;
    } catch {
      setWorkflowBound(false);
      return false;
    }
  }, []);

  useEffect(() => {
    void refreshList().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "list failed");
    });
    void refreshWorkflowBinding();
  }, [refreshList, refreshWorkflowBinding]);

  async function openBundle(
    id: string,
    options?: { preferWiki?: boolean },
  ) {
    const preferWiki = options?.preferWiki ?? false;
    setSelected(id);
    setConceptId(null);
    setConceptMd("");
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch(
        `/api/okf/okf/bundles/${encodeURIComponent(id)}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const payload = (await res.json()) as BundleDetail;
      setDetail(payload);
      const wiki = payload.wiki_md || "";
      setWikiDraft(wiki);
      setWikiSaved(wiki);
      const openWiki = preferWiki || Boolean(wiki.trim());
      setWikiMode(wiki.trim() ? "edit" : "preview");
      setActiveTab(openWiki && wiki.trim() ? "wiki" : "index");
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    } finally {
      setBusy(false);
    }
  }

  async function openConcept(id: string) {
    if (!selected) {
      return;
    }
    setConceptId(id);
    setBusy(true);
    setError(null);
    try {
      const res = await apiFetch(
        `/api/okf/okf/bundles/${encodeURIComponent(selected)}?concept_id=${encodeURIComponent(id)}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const body = (await res.json()) as {
        markdown?: string;
        concepts?: string[];
        index_md?: string;
      };
      if (body.markdown) {
        setConceptMd(body.markdown);
      } else {
        setConceptMd(
          `# ${id}\n\nOpen via MCP okf_bundle_get or download the bundle.`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "concept failed");
    } finally {
      setBusy(false);
    }
  }

  async function generateBundle() {
    setBusy(true);
    setError(null);
    setInfo(null);
    setRunId(null);
    setRunStatus(null);
    try {
      const res = await apiFetch("/api/okf/okf/export", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          query: query.trim() || null,
          max_docs: 40,
        }),
      });
      const body = (await res.json()) as {
        bundle?: OkfBundle;
        detail?: string;
      };
      if (!res.ok || !body.bundle) {
        throw new Error(body.detail || `export failed (${res.status})`);
      }
      await refreshList();
      await openBundle(body.bundle.bundle_id, { preferWiki: true });
      setInfo(
        "Scoped bundle exported. Edit the LLMWiki tab, or use Generate wiki (agent) for an answered page.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "export failed");
    } finally {
      setBusy(false);
    }
  }

  async function generateWikiWithAgent() {
    const goal = query.trim();
    if (!goal) {
      setError("Enter a query before generating a wiki with the agent.");
      return;
    }
    const bound = await refreshWorkflowBinding();
    if (!bound) {
      setError(
        `Agent workflow “${LLM_WIKI_WORKFLOW}” is not registered. Restart tkeir-agent so it loads datasets/osint/workflows (or packs/osint in the image).`,
      );
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    setRunId(null);
    setRunStatus("queued");
    setRunSteps(0);
    try {
      const startRes = await apiFetch("/api/agent/agent/runs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          workflow: LLM_WIKI_WORKFLOW,
          goal,
          params: {
            query: goal,
            topic: goal,
            max_docs: 40,
            max_wiki_chunks: 8,
            use_wiki: true,
            search_mode: "both",
          },
        }),
      });
      const startBody = (await startRes.json()) as {
        run_id?: string;
        detail?: string;
      };
      if (!startRes.ok || !startBody.run_id) {
        throw new Error(
          startBody.detail || `agent start failed (${startRes.status})`,
        );
      }
      setRunId(startBody.run_id);
      setInfo(
        `Agent workflow ${LLM_WIKI_WORKFLOW} started (${startBody.run_id}).`,
      );
      let bundleId: string | null = null;
      let lastStatus = "queued";
      for (let attempt = 0; attempt < 240; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const pollRes = await apiFetch(
          `/api/agent/agent/runs/${encodeURIComponent(startBody.run_id)}`,
          { cache: "no-store" },
        );
        if (!pollRes.ok) {
          throw new Error(await pollRes.text());
        }
        const payload = (await pollRes.json()) as AgentRunPayload;
        lastStatus = payload.run?.status || lastStatus;
        setRunStatus(lastStatus);
        setRunSteps(payload.steps?.length ?? 0);
        bundleId = bundleIdFromRun(payload) || bundleId;
        if (TERMINAL_STATUSES.has(lastStatus)) {
          if (lastStatus !== "succeeded") {
            throw new Error(
              payload.run?.error || `agent run ${lastStatus}`,
            );
          }
          break;
        }
      }
      if (lastStatus !== "succeeded") {
        throw new Error(
          `agent run timed out (status=${lastStatus}). Check Agents for run ${startBody.run_id}.`,
        );
      }
      if (!bundleId) {
        throw new Error(
          "Agent succeeded but no bundle_id was returned. Refresh bundles and open the latest scoped export.",
        );
      }
      await refreshList();
      await openBundle(bundleId, { preferWiki: true });
      setWikiMode("edit");
      setActiveTab("wiki");
      setInfo(
        "LLMWiki generated from retrieved results. Review and edit below, then Save or Add to My files.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "agent wiki failed");
    } finally {
      setBusy(false);
    }
  }

  async function saveWiki() {
    if (!selected) {
      return;
    }
    const markdown = wikiDraft.trim();
    if (!markdown) {
      setError("Wiki markdown must not be empty");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch(
        `/api/okf/okf/bundles/${encodeURIComponent(selected)}/wiki`,
        {
          method: "PUT",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ markdown: wikiDraft }),
        },
      );
      const body = (await res.json()) as {
        detail?: string | { detail?: string };
      };
      if (!res.ok) {
        throw new Error(
          errorDetail(body) || `save wiki failed (${res.status})`,
        );
      }
      setWikiSaved(wikiDraft);
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              wiki_md: wikiDraft,
              has_wiki: true,
            }
          : prev,
      );
      setInfo("Wiki saved to the OKF bundle.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "save wiki failed");
    } finally {
      setBusy(false);
    }
  }

  async function addWikiToMyFiles() {
    if (!selected) {
      return;
    }
    const markdown = wikiDraft.trim();
    if (!markdown) {
      setError("Wiki markdown must not be empty");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch(
        `/api/okf/okf/bundles/${encodeURIComponent(selected)}/publish-wiki`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ markdown: wikiDraft }),
        },
      );
      const body = (await res.json()) as {
        workspace_path?: string;
        ingest_id?: string;
        detail?: string | { detail?: string };
      };
      if (!res.ok) {
        throw new Error(
          errorDetail(body) || `publish failed (${res.status})`,
        );
      }
      setWikiSaved(wikiDraft);
      setDetail((prev) =>
        prev
          ? {
              ...prev,
              wiki_md: wikiDraft,
              has_wiki: true,
            }
          : prev,
      );
      setInfo(
        `Wiki saved to My files as ${body.workspace_path || "wiki/*.md"}` +
          (body.ingest_id ? ` (ingest ${body.ingest_id})` : "") +
          ". Open My files to browse it.",
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "publish wiki failed");
    } finally {
      setBusy(false);
    }
  }

  const hasWiki = Boolean(
    detail?.has_wiki ||
      (detail?.wiki_md && detail.wiki_md.trim()) ||
      wikiDraft.trim(),
  );
  const wikiDirty = wikiDraft !== wikiSaved;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold">LLM Wiki</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Generate scoped OKF knowledge bundles with an editable LLMWiki page,
          then publish into My files.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate from query</CardTitle>
          <CardDescription>
            Bound workflow:{" "}
            <code>{boundWorkflow}</code>
            {workflowBound === false
              ? " (not registered on agent — restart tkeir-agent)"
              : workflowBound
                ? " (ready)"
                : " (checking…)"}
            . Scope results → analyse → review → write wiki, then edit the page.
            Or export a scoped OKF bundle without the agent.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <label className="flex-1 space-y-1 text-sm">
            <span className="text-muted-foreground">Query</span>
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              disabled={busy}
              placeholder="What is the status of Project ATLAS?"
            />
          </label>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Button
              onClick={() => void generateWikiWithAgent()}
              disabled={busy || !query.trim() || workflowBound === false}
            >
              Generate wiki (agent)
            </Button>
            <Button
              variant="outline"
              onClick={() => void generateBundle()}
              disabled={busy}
            >
              Export bundle only
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void refreshWorkflowBinding()}
              disabled={busy}
            >
              Refresh binding
            </Button>
          </div>
          {runId ? (
            <p className="text-xs text-muted-foreground">
              Run <span className="font-mono">{runId}</span>
              {runStatus ? ` · ${runStatus}` : ""}
              {runSteps > 0 ? ` · ${runSteps} step(s)` : ""}
            </p>
          ) : null}
        </CardContent>
      </Card>

      {error ? (
        <p className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      ) : null}
      {info ? (
        <p className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm text-foreground">
          {info}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Bundles</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {bundles.length === 0 ? (
              <p className="text-sm text-muted-foreground">No bundles yet.</p>
            ) : (
              bundles.map((b) => (
                <button
                  key={b.bundle_id}
                  type="button"
                  onClick={() => void openBundle(b.bundle_id)}
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                    selected === b.bundle_id
                      ? "border-primary bg-primary/5"
                      : "hover:bg-muted/40"
                  }`}
                >
                  <div className="font-medium truncate">{b.bundle_id}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <Badge variant="secondary">{b.concept_count} concepts</Badge>
                    {b.query ? <Badge variant="outline">scoped</Badge> : null}
                  </div>
                </button>
              ))
            )}
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => void refreshList()}
              disabled={busy}
            >
              Refresh
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-2">
            <div>
              <CardTitle className="text-base">
                {selected ? selected : "Select a bundle"}
              </CardTitle>
              <CardDescription>
                Index, editable LLMWiki, concepts, and download.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              {selected && hasWiki ? (
                <Button
                  variant="default"
                  size="sm"
                  disabled={busy}
                  onClick={() => void addWikiToMyFiles()}
                >
                  Add wiki to My files
                </Button>
              ) : null}
              {selected ? (
                <Button asChild variant="secondary" size="sm">
                  <a
                    href={`/api/okf/okf/bundles/${encodeURIComponent(selected)}/download`}
                  >
                    Download
                  </a>
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent>
            {!detail ? (
              <p className="text-sm text-muted-foreground">
                Choose a bundle from the list.
              </p>
            ) : (
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                  <TabsTrigger value="index">Index</TabsTrigger>
                  <TabsTrigger value="wiki">
                    Wiki{wikiDirty ? " *" : ""}
                  </TabsTrigger>
                  <TabsTrigger value="concepts">Concepts</TabsTrigger>
                  <TabsTrigger value="concept" disabled={!conceptId}>
                    Concept
                  </TabsTrigger>
                </TabsList>
                <TabsContent value="index" className="prose prose-sm max-w-none">
                  <MarkdownContent content={detail.index_md || ""} />
                </TabsContent>
                <TabsContent value="wiki" className="space-y-3">
                  {!hasWiki ? (
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">
                        No LLMWiki page yet. Run{" "}
                        <strong>Generate wiki (agent)</strong> to answer your
                        query from retrieved results, then edit the page here.
                      </p>
                      <Button
                        size="sm"
                        disabled={busy || !query.trim()}
                        onClick={() => void generateWikiWithAgent()}
                      >
                        Generate wiki (agent)
                      </Button>
                    </div>
                  ) : (
                    <>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant={wikiMode === "edit" ? "default" : "outline"}
                            disabled={busy}
                            onClick={() => setWikiMode("edit")}
                          >
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant={
                              wikiMode === "preview" ? "default" : "outline"
                            }
                            disabled={busy}
                            onClick={() => setWikiMode("preview")}
                          >
                            Preview
                          </Button>
                          {wikiDirty ? (
                            <Badge variant="outline">Unsaved</Badge>
                          ) : null}
                        </div>
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            disabled={busy || !wikiDirty}
                            onClick={() => void saveWiki()}
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            disabled={busy}
                            onClick={() => void addWikiToMyFiles()}
                          >
                            Add to My files
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busy || !query.trim()}
                            onClick={() => void generateWikiWithAgent()}
                          >
                            Regenerate (agent)
                          </Button>
                        </div>
                      </div>
                      {wikiMode === "edit" ? (
                        <textarea
                          value={wikiDraft}
                          onChange={(e) => setWikiDraft(e.target.value)}
                          disabled={busy}
                          spellCheck={false}
                          className="min-h-[28rem] w-full rounded-md border bg-background px-3 py-2 font-mono text-sm leading-relaxed text-foreground outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label="Edit LLMWiki markdown"
                        />
                      ) : (
                        <div className="min-h-[28rem] rounded-md border px-3 py-2">
                          <MarkdownContent content={wikiDraft} />
                        </div>
                      )}
                    </>
                  )}
                </TabsContent>
                <TabsContent value="concepts" className="space-y-2">
                  {(detail.concepts || []).map((cid) => (
                    <button
                      key={cid}
                      type="button"
                      className="block w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/40"
                      onClick={() => void openConcept(cid)}
                    >
                      {cid}
                    </button>
                  ))}
                </TabsContent>
                <TabsContent value="concept" className="prose prose-sm max-w-none">
                  <MarkdownContent content={conceptMd} />
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
