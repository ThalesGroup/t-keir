"use client";

import { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpen,
  FileText,
  Loader2,
  Network,
  Save,
  Send,
} from "lucide-react";

import { AgentRunActivity } from "@/components/agent-run-activity";
import { MarkdownContent } from "@/components/markdown-content";
import { OntologyNavigator } from "@/components/ontology-navigator";
import { OntologyReasonGraph } from "@/components/ontology-reason-graph";
import { ReporterChunkPanel } from "@/components/reporter-chunk-panel";
import { SaveToMyFilesForm } from "@/components/save-to-my-files-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getAnalyzedDocument,
  ontologyQueryOptions,
  querySearch,
  RagApiError,
} from "@/lib/api";
import { weightMapsFromOntology } from "@/lib/ontology-graph";
import {
  LLM_WIKI_WORKFLOW,
  OKF_WIKI_PROMPT,
  resolvePersonaWorkflowPreset,
} from "@/lib/persona-workflows";
import {
  type AgentRunPayload,
  REPORTER_STATUS_STEPS,
  TERMINAL_RUN_STATUSES,
  alignOntologyToWikiEvidence,
  buildWikiGrabChunks,
  bundleIdFromRun,
  errorDetail,
  extractWikiEvidenceRefs,
  fuseGrabAndWikiOntology,
  mergeOntologyJsonLd,
  sleep,
  suggestedWikiMyFilesTarget,
  wikiMarkdownFromRun,
} from "@/lib/reporter";
import {
  type FusedOntology,
  type SearchChunkHit,
  type SearchResponse,
  type SemanticEntity,
  type SemanticKeyword,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";
import { apiFetch } from "@/src/auth/useApiClient";

const SHARE_ROLES = ["c2-j2-analyst", "c2-moc-watch", "c2-j2x-humint"];

/** Default node budget for Reporter Grab+Wiki ontology (by weight). */
const DEFAULT_GRAPH_MAX_NODES = 24;
const GRAPH_MAX_NODES_MIN = 4;
const GRAPH_MAX_NODES_MAX = 80;

type BundleDetail = {
  bundle_id: string;
  index_md?: string;
  concepts?: string[];
  wiki_md?: string;
  has_wiki?: boolean;
};

interface ReporterPanelProps {
  agentAvailable: boolean;
}

export function ReporterPanel({ agentAvailable }: ReporterPanelProps) {
  const { authEnabled, roles, activePersonaId, runtimeConfig } = useAuth();
  const persona = useMemo(
    () => resolvePersonaWorkflowPreset({ roles, activePersonaId }),
    [roles, activePersonaId],
  );
  const canShareToCommander =
    !authEnabled || SHARE_ROLES.some((role) => roles.includes(role));

  const [query, setQuery] = useState(persona.goal);
  const [hits, setHits] = useState(20);
  const [busy, setBusy] = useState(false);
  /** Which part of the fused Grab→wiki pipeline is active (for button label). */
  const [pipelinePhase, setPipelinePhase] = useState<"idle" | "grab" | "wiki">(
    "idle",
  );
  const [savingWiki, setSavingWiki] = useState(false);
  const [wikiSaveOpen, setWikiSaveOpen] = useState(false);
  const [wikiSavedPath, setWikiSavedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Phase 1 — retrieval
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(
    null,
  );
  // Phase 1 ontology (grab) vs Phase 2 ontology (wiki evidence)
  const [ontology, setOntology] = useState<FusedOntology | null>(null);
  const [wikiOntology, setWikiOntology] = useState<FusedOntology | null>(null);
  const [ontologyLoading, setOntologyLoading] = useState(false);
  const [ontologyKey, setOntologyKey] = useState("idle");
  const [wikiOntologyKey, setWikiOntologyKey] = useState("idle");
  const [wikiOntologyNote, setWikiOntologyNote] = useState<string | null>(null);
  const [activeChunkIds, setActiveChunkIds] = useState<Set<string> | null>(
    null,
  );
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [graphMaxNodes, setGraphMaxNodes] = useState(DEFAULT_GRAPH_MAX_NODES);

  // Phase 2 — wiki
  const [bundleId, setBundleId] = useState<string | null>(null);
  const [bundleDetail, setBundleDetail] = useState<BundleDetail | null>(null);
  const [wikiDraft, setWikiDraft] = useState("");
  const [wikiMode, setWikiMode] = useState<"edit" | "preview">("edit");
  const [wikiRunId, setWikiRunId] = useState<string | null>(null);
  const [wikiRunStatus, setWikiRunStatus] = useState<string | null>(null);
  const [wikiRunPayload, setWikiRunPayload] =
    useState<AgentRunPayload | null>(null);

  const retrievedChunks = useMemo(() => {
    if (!searchResponse) return [] as SearchChunkHit[];
    const chunks = [...searchResponse.chunks];
    chunks.sort((a, b) => b.score - a.score);
    return chunks;
  }, [searchResponse]);

  const grabComplete = Boolean(searchResponse && retrievedChunks.length > 0);
  const wikiComplete = Boolean(wikiDraft.trim());

  const wikiEvidenceChunkIds = useMemo(() => {
    if (!wikiDraft.trim() && !wikiRunPayload) return null;
    const refs = extractWikiEvidenceRefs(wikiDraft, wikiRunPayload);
    if (!refs.chunkIds.length) return null;
    return new Set(refs.chunkIds);
  }, [wikiDraft, wikiRunPayload]);

  /** Fused Grab + Wiki ontology — pruned in the graph by weight (Nodes control). */
  const displayWikiOntology = useMemo(
    () => fuseGrabAndWikiOntology(ontology, wikiOntology),
    [ontology, wikiOntology],
  );

  const displayWikiWeights = useMemo(
    () => weightMapsFromOntology(displayWikiOntology),
    [displayWikiOntology],
  );

  /** Highlight wiki-aligned labels on the comprehensive graph (does not prune). */
  const wikiPreferredLabels = useMemo(() => {
    if (!displayWikiOntology) return [] as string[];
    const wikiLabels = new Set(
      (wikiOntology?.entities ?? []).map((entity) =>
        entity.label.trim().toLowerCase(),
      ),
    );
    return [...displayWikiOntology.entities]
      .sort((a, b) => {
        const aWiki = wikiLabels.has(a.label.trim().toLowerCase()) ? 1 : 0;
        const bWiki = wikiLabels.has(b.label.trim().toLowerCase()) ? 1 : 0;
        if (bWiki !== aWiki) return bWiki - aWiki;
        return b.chunk_ids.length - a.chunk_ids.length;
      })
      .slice(0, 24)
      .map((entity) => entity.label)
      .concat(
        [...(displayWikiOntology.keywords ?? [])]
          .sort((a, b) => b.chunk_ids.length - a.chunk_ids.length)
          .slice(0, 12)
          .map((keyword) => keyword.label),
      );
  }, [displayWikiOntology, wikiOntology]);

  /**
   * Dual-index Grab. Sets search/ontology state so results paint immediately.
   * Returns ranked chunks for the wiki step (React state may not have flushed yet).
   */
  async function performGrab(trimmed: string): Promise<SearchChunkHit[]> {
    setPipelinePhase("grab");
    setOntologyLoading(true);
    setOntologyKey(trimmed);
    setActiveChunkIds(null);
    setActiveLabel(null);
    try {
      const { response } = await querySearch({
        query: trimmed,
        language: "en",
        hits,
        // Dual Vespa schemas (global + user) — required for wiki evidence.
        search_mode: "both",
        ...ontologyQueryOptions(runtimeConfig),
      });
      setSearchResponse(response);
      setOntology(response.ontology ?? null);
      const chunks = [...response.chunks].sort((a, b) => b.score - a.score);
      setInfo(
        `Retrieved ${response.documents.length} document(s), ${response.chunks.length} chunk(s) via dual-index (global+user). Generating persona wiki…`,
      );
      // Let React paint Grab results before the wiki agent starts.
      await sleep(50);
      return chunks;
    } catch (err) {
      const message =
        err instanceof RagApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "retrieval failed";
      setSearchResponse(null);
      setOntology(null);
      throw new Error(message);
    } finally {
      setOntologyLoading(false);
    }
  }

  async function refreshWikiOntology(
    goal: string,
    payload: AgentRunPayload,
    wikiMarkdown: string,
  ) {
    setOntologyLoading(true);
    setWikiOntologyNote(null);
    setActiveChunkIds(null);
    setActiveLabel(null);
    try {
      const refs = extractWikiEvidenceRefs(wikiMarkdown, payload);
      const jsonLdParts: string[] = [];
      for (const docId of refs.docIds.slice(0, 16)) {
        try {
          const doc = await getAnalyzedDocument(docId, runtimeConfig);
          const ld = doc.document_ontology?.json_ld;
          if (typeof ld === "string" && ld.trim()) {
            jsonLdParts.push(ld);
          }
        } catch {
          /* analyzed dump may not have this source_ref */
        }
      }
      // Prefer hybrid search (fast, returns fused ontology) over full RAG.
      const { response } = await querySearch({
        query: goal,
        language: "en",
        hits: 40,
        search_mode: "both",
        ...ontologyQueryOptions(runtimeConfig),
        ontology_json_ld: mergeOntologyJsonLd(jsonLdParts),
      });
      const aligned = alignOntologyToWikiEvidence(
        response.ontology ?? null,
        wikiMarkdown,
        payload,
      );
      const resolved = aligned ?? ontology;
      setWikiOntology(resolved);
      setWikiOntologyKey(
        `wiki:${goal}:${resolved?.entities.length ?? 0}:${Date.now()}`,
      );
      const ent = resolved?.entities.length ?? 0;
      const kw = resolved?.keywords.length ?? 0;
      const usedFallback = !aligned && Boolean(ontology);
      setWikiOntologyNote(
        usedFallback
          ? `Wiki search returned no ontology — showing Grab ontology (${ent} entities / ${kw} keywords).`
          : `Fused ontology from search + ${jsonLdParts.length} cited analyzed doc(s)` +
              ` · ${ent} entities / ${kw} keywords` +
              (refs.chunkIds.length
                ? ` · ${refs.chunkIds.length} citation(s)`
                : ""),
      );
    } catch (err) {
      if (ontology) {
        setWikiOntology(ontology);
        setWikiOntologyKey(`wiki:${goal}:fallback:${Date.now()}`);
        setWikiOntologyNote(
          err instanceof Error
            ? `Wiki ontology refresh failed (${err.message}); showing Grab ontology.`
            : "Wiki ontology refresh failed; showing Grab ontology.",
        );
      } else {
        setWikiOntology(null);
        setWikiOntologyKey(`wiki:${goal}:empty`);
        setWikiOntologyNote(
          err instanceof Error
            ? `Could not refresh wiki ontology: ${err.message}`
            : "Could not refresh wiki ontology",
        );
      }
    } finally {
      setOntologyLoading(false);
    }
  }

  async function openBundle(id: string): Promise<string> {
    const res = await apiFetch(
      `/api/okf/okf/bundles/${encodeURIComponent(id)}`,
      { cache: "no-store" },
    );
    if (!res.ok) {
      let detail = await res.text();
      try {
        const parsed = JSON.parse(detail) as {
          detail?: string | { detail?: string };
        };
        detail = errorDetail(parsed) || detail;
      } catch {
        /* keep raw */
      }
      throw new Error(
        detail || `OKF bundle ${id.slice(0, 8)}… not found (${res.status})`,
      );
    }
    const payload = (await res.json()) as BundleDetail;
    setBundleId(id);
    setBundleDetail(payload);
    const wiki = payload.wiki_md || "";
    setWikiDraft(wiki);
    setWikiMode(wiki.trim() ? "edit" : "preview");
    return wiki;
  }

  async function performGenerateWiki(
    goal: string,
    evidenceChunks: SearchChunkHit[],
  ) {
    if (!agentAvailable) {
      throw new Error("Agent service unavailable. Start it with make agent.");
    }
    if (!evidenceChunks.length) {
      throw new Error(
        "Grab returned no chunks — wiki needs retrieved passages.",
      );
    }
    setPipelinePhase("wiki");
    setWikiRunId(null);
    setWikiRunStatus("queued");
    setWikiRunPayload(null);
    setWikiOntology(null);
    setWikiOntologyNote(null);

    const wfRes = await apiFetch("/api/agent/agent/workflows", {
      cache: "no-store",
    });
    if (wfRes.ok) {
      const body = (await wfRes.json()) as { workflows?: string[] };
      if (!(body.workflows ?? []).includes(LLM_WIKI_WORKFLOW)) {
        throw new Error(
          `Agent workflow “${LLM_WIKI_WORKFLOW}” is not registered. Restart tkeir-agent.`,
        );
      }
    }
    // Grab chunks + ## Information from same-parent siblings (dual-index Grab).
    // Persona wiki prompt supplies Structured facts seed (OKF-compatible).
    const grabChunks = buildWikiGrabChunks(evidenceChunks, 8);
    const wikiPrompt = persona.wikiPrompt || OKF_WIKI_PROMPT;
    const startRes = await apiFetch("/api/agent/agent/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        workflow: LLM_WIKI_WORKFLOW,
        goal,
        params: {
          query: goal,
          topic: goal,
          max_docs: 8,
          max_wiki_chunks: grabChunks.length,
          search_mode: "both",
          prompt_name: wikiPrompt,
          wiki_agent: wikiPrompt,
          chunks: grabChunks,
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
    setWikiRunId(startBody.run_id);
    setInfo(
      `Persona wiki (${wikiPrompt}) started with ${grabChunks.length} grab chunk(s) (${startBody.run_id}).`,
    );

    // Single-pass wiki should finish in a few minutes; allow ~10 min.
    let last: AgentRunPayload = {};
    const wikiPollAttempts = 300;
    const wikiPollMs = 2000;
    for (let attempt = 0; attempt < wikiPollAttempts; attempt += 1) {
      await sleep(wikiPollMs);
      const pollRes = await apiFetch(
        `/api/agent/agent/runs/${encodeURIComponent(startBody.run_id)}`,
        { cache: "no-store" },
      );
      if (!pollRes.ok) throw new Error(await pollRes.text());
      last = (await pollRes.json()) as AgentRunPayload;
      const status = last.run?.status || "";
      setWikiRunStatus(status);
      setWikiRunPayload(last);
      const progress = (last.blackboard || [])
        .filter((e) => e?.kind === "wiki_progress")
        .at(-1);
      const evidenceMode = (last.blackboard || []).some(
        (e) => e?.mode === "evidence_chunks",
      );
      const chunkHint = progress?.chunk_index
        ? ` · wiki ${progress.chunk_index}/${progress.chunk_total || "?"} (${progress.wiki_chars || 0} chars)`
        : evidenceMode
          ? ` · evidence bundle · ${grabChunks.length} chunk(s)`
          : ` · ${grabChunks.length} grab chunk(s)`;
      if (attempt % 3 === 0) {
        setInfo(
          `Persona wiki running (${status || "…"})${chunkHint} · ` +
            `${startBody.run_id.slice(0, 8)}…`,
        );
      }
      if (TERMINAL_RUN_STATUSES.has(status)) {
        if (status !== "succeeded") {
          throw new Error(last.run?.error || `agent run ${status}`);
        }
        break;
      }
    }
    let id = bundleIdFromRun(last);
    if ((last.run?.status || "") !== "succeeded") {
      // Agent may still finish after the poll window — recover partial wiki.
      if (id) {
        try {
          const recovered = await openBundle(id);
          if (
            recovered.trim() &&
            !recovered.includes("_Iterative wiki — folding")
          ) {
            setInfo(
              `Wiki recovered from bundle ${id.slice(0, 8)}… while agent was still running. Refresh if it updates.`,
            );
            return;
          }
        } catch {
          /* fall through */
        }
      }
      throw new Error(
        `Persona wiki timed out (status=${last.run?.status || "unknown"}). ` +
          `Confirm Grab sent ${grabChunks.length} chunk(s), prompt=${wikiPrompt}, restart tkeir-agent, then retry.`,
      );
    }
    id = bundleIdFromRun(last);
    if (!id) {
      throw new Error(
        "Agent succeeded but no bundle_id was returned. Try again.",
      );
    }
    let loadedWiki = "";
    try {
      loadedWiki = await openBundle(id);
      setInfo(
        "Persona wiki generated — Grab search + wiki are shown together; ontology refreshes on the left.",
      );
    } catch (openErr) {
      const fromRun = wikiMarkdownFromRun(last);
      if (!fromRun) {
        throw openErr;
      }
      setBundleId(id);
      setWikiDraft(fromRun);
      setWikiMode("edit");
      loadedWiki = fromRun;
      setInfo(
        `Wiki recovered from the agent run (OKF GET failed for bundle ${id.slice(0, 8)}…). ` +
          "Try Save wiki — if that also fails, confirm you are logged in as the same user that owns the bundle (e.g. analyst).",
      );
    }

    // Fuse Grab (search) with the wiki: refresh retrieval on the same query
    // so both evidence chunks and wiki content are available together.
    try {
      const { response } = await querySearch({
        query: goal,
        language: "en",
        hits,
        search_mode: "both",
        ...ontologyQueryOptions(runtimeConfig),
      });
      setSearchResponse(response);
      setOntology(response.ontology ?? null);
      setOntologyKey(`grab+wiki:${goal}`);
    } catch {
      /* keep prior Grab results if any */
    }

    void refreshWikiOntology(
      goal,
      last,
      loadedWiki || wikiMarkdownFromRun(last) || "",
    );
  }

  /** Single primary action: Grab / retrieve, show results, then generate wiki. */
  async function grabAndGenerateWiki() {
    const goal = query.trim();
    if (!goal) {
      setError("Enter a query to retrieve and generate the wiki.");
      return;
    }
    if (!agentAvailable) {
      setError("Agent service unavailable. Start it with make agent.");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    setPipelinePhase("grab");
    try {
      const chunks = await performGrab(goal);
      await performGenerateWiki(goal, chunks);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Grab & wiki generation failed",
      );
    } finally {
      setBusy(false);
      setPipelinePhase("idle");
    }
  }

  const wikiMyFilesTarget = useMemo(
    () => suggestedWikiMyFilesTarget(query.trim() || persona.topic),
    [query, persona.topic],
  );

  async function saveWiki() {
    if (!wikiDraft.trim()) {
      setError("Wiki markdown must not be empty.");
      return;
    }
    setWikiSaveOpen(true);
    setError(null);
    setInfo(null);
  }

  async function confirmSaveWikiToMyFiles(
    path: string,
  ): Promise<string | null> {
    if (!wikiDraft.trim()) {
      setError("Wiki markdown must not be empty.");
      return null;
    }
    const dest = path.trim().replace(/^\/+/, "");
    if (!dest) {
      setError("Choose a filename under My files.");
      return null;
    }
    setSavingWiki(true);
    setError(null);
    setInfo(null);
    try {
      const parent = dest.includes("/")
        ? dest.split("/").slice(0, -1).join("/")
        : "";
      if (parent) {
        const mkdirRes = await apiFetch("/api/ingest/workspace/mkdir", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ path: parent }),
        });
        if (!mkdirRes.ok && mkdirRes.status !== 409) {
          // 409 / already exists is fine; other errors still try publish.
          const detail = await mkdirRes.text();
          if (mkdirRes.status >= 500) {
            throw new Error(detail || `mkdir failed (${mkdirRes.status})`);
          }
        }
      }

      // Prefer OKF publish (persists bundle wiki.md + copies to My files).
      if (bundleId) {
        const res = await apiFetch(
          `/api/okf/okf/bundles/${encodeURIComponent(bundleId)}/publish-wiki`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ markdown: wikiDraft, path: dest }),
          },
        );
        let body: {
          workspace_path?: string;
          ingest_id?: string;
          detail?: string | { detail?: string };
        } = {};
        try {
          body = (await res.json()) as typeof body;
        } catch {
          /* non-JSON */
        }
        if (!res.ok) {
          throw new Error(
            errorDetail(body) || `save wiki to My files failed (${res.status})`,
          );
        }
        setBundleDetail((prev) =>
          prev
            ? { ...prev, wiki_md: wikiDraft, has_wiki: true }
            : {
                bundle_id: bundleId,
                wiki_md: wikiDraft,
                has_wiki: true,
              },
        );
        const saved = body.workspace_path || dest;
        setWikiSavedPath(saved);
        setWikiSaveOpen(false);
        setInfo(
          `Wiki saved to My files as ${saved}` +
            (body.ingest_id ? ` (ingest ${body.ingest_id})` : "") +
            ".",
        );
        return saved;
      }

      // Fallback: direct workspace upload when no OKF bundle id.
      const blob = new Blob([wikiDraft], { type: "text/markdown" });
      const file = new File([blob], dest.split("/").pop() || "wiki.md", {
        type: "text/markdown",
      });
      const form = new FormData();
      form.append("file", file);
      form.append("path", dest);
      form.append("index", "false");
      const res = await apiFetch("/api/ingest/workspace/upload", {
        method: "POST",
        body: form,
      });
      const body = (await res.json()) as {
        path?: string;
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(body.detail || `upload failed (${res.status})`);
      }
      const saved = body.path || dest;
      setWikiSavedPath(saved);
      setWikiSaveOpen(false);
      setInfo(`Wiki saved to My files as ${saved}.`);
      return saved;
    } catch (err) {
      setError(err instanceof Error ? err.message : "save wiki failed");
      return null;
    } finally {
      setSavingWiki(false);
    }
  }

  async function sendWikiToCommander() {
    if (!wikiDraft.trim()) {
      setError("Wiki markdown must not be empty.");
      return;
    }
    let path = wikiSavedPath;
    if (!path) {
      const target = suggestedWikiMyFilesTarget(
        query.trim() || persona.topic,
      );
      const dest = [target.directory, target.filename].filter(Boolean).join("/");
      path = await confirmSaveWikiToMyFiles(dest);
      if (!path) return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const res = await apiFetch("/api/ingest/workspace/copy-to", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          paths: [path],
          target_user_space: "commander",
        }),
      });
      const body = (await res.json()) as {
        copied_count?: number;
        dest_prefix?: string;
        detail?: string;
        errors?: { path: string; error: string }[];
      };
      if (!res.ok) {
        throw new Error(body.detail || `share failed (${res.status})`);
      }
      const errCount = body.errors?.length ?? 0;
      setInfo(
        `Sent wiki to commander My files` +
          (body.dest_prefix ? ` (${body.dest_prefix}/)` : "") +
          (errCount ? ` — ${errCount} failed` : ""),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "share failed");
    } finally {
      setBusy(false);
    }
  }

  const handleSelectEntity = useCallback(
    (entity: SemanticEntity) => {
      if (activeLabel === entity.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      setActiveChunkIds(new Set(entity.chunk_ids));
      setActiveLabel(entity.label);
      const first = entity.chunk_ids[0];
      if (first) {
        window.setTimeout(() => {
          document
            .querySelector(`[data-chunk-id="${CSS.escape(first)}"]`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 50);
      }
    },
    [activeLabel],
  );

  const handleSelectKeyword = useCallback(
    (keyword: SemanticKeyword) => {
      if (activeLabel === keyword.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      setActiveChunkIds(new Set(keyword.chunk_ids));
      setActiveLabel(keyword.label);
      const first = keyword.chunk_ids[0];
      if (first) {
        window.setTimeout(() => {
          document
            .querySelector(`[data-chunk-id="${CSS.escape(first)}"]`)
            ?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 50);
      }
    },
    [activeLabel],
  );

  const wikiBusy = busy && pipelinePhase === "wiki";
  const grabBusy = busy && pipelinePhase === "grab";

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">
          Reporter
        </p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight">
          Grab &amp; persona wiki
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Retrieve grounded passages, generate an editable OKF persona wiki (
          <code>{persona.wikiPrompt}</code>), then save to My files or send to
          the commander.
        </p>
        {!agentAvailable && (
          <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
            Agent service offline — wiki generation needs{" "}
            <code className="rounded bg-muted px-1">make agent</code>.
          </p>
        )}
      </div>

      <ol className="grid gap-2 sm:grid-cols-2">
        {REPORTER_STATUS_STEPS.map((item) => {
          const done =
            (item.id === "grab" && grabComplete) ||
            (item.id === "wiki" && wikiComplete);
          return (
            <li
              key={item.id}
              className={cn(
                "flex flex-col rounded-lg border px-3 py-3 text-sm",
                done && "border-emerald-500/40",
              )}
            >
              <span className="flex items-center gap-2 font-medium">
                <Badge variant={done ? "default" : "outline"}>
                  {item.title}
                </Badge>
                {done && (
                  <Badge
                    variant="outline"
                    className="ml-auto border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                  >
                    ready
                  </Badge>
                )}
              </span>
              <span className="mt-1 text-xs text-muted-foreground">
                {item.blurb}
              </span>
            </li>
          );
        })}
      </ol>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Reporter</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {info && (
        <Alert>
          <FileText className="h-4 w-4" />
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{info}</AlertDescription>
        </Alert>
      )}

      {/* Query + primary action */}
      <section className="space-y-3 rounded-lg border p-4">
        <form
          className="flex flex-col gap-3 lg:flex-row lg:items-end"
          onSubmit={(event) => {
            event.preventDefault();
            void grabAndGenerateWiki();
          }}
        >
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Intelligence question or topic…"
            disabled={busy}
            className="flex-1"
          />
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Documents
            <Input
              type="number"
              min={1}
              max={100}
              value={hits}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  setHits(Math.min(100, Math.max(1, parsed)));
                }
              }}
              className="w-24"
              aria-label="Number of documents to retrieve"
              disabled={busy}
            />
          </label>
          <Button
            type="submit"
            disabled={busy || !agentAvailable || !query.trim()}
          >
            {busy ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <BookOpen className="h-4 w-4" />
            )}
            {grabBusy
              ? "Retrieving…"
              : wikiBusy
                ? "Generating wiki…"
                : "Grab & generate wiki"}
          </Button>
        </form>
        <p className="text-xs text-muted-foreground">
          Retrieves dual-index passages, shows them below, then folds them into
          a persona wiki via <code>{persona.wikiPrompt}</code>.
        </p>
      </section>

      {/* Fused Grab + Wiki workspace */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {wikiRunId && (
            <Badge variant="outline">
              wiki {wikiRunStatus || "running"} · {wikiRunId.slice(0, 8)}
            </Badge>
          )}
          {bundleId && (
            <Badge variant="outline">bundle {bundleId.slice(0, 10)}</Badge>
          )}
          {wikiSavedPath && (
            <Badge
              variant="outline"
              className="border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
            >
              My files · {wikiSavedPath}
            </Badge>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="ml-auto"
            disabled={
              busy ||
              ontologyLoading ||
              !query.trim() ||
              !wikiDraft.trim()
            }
            onClick={() =>
              void refreshWikiOntology(
                query.trim(),
                wikiRunPayload ?? {},
                wikiDraft,
              )
            }
          >
            {ontologyLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Network className="h-4 w-4" />
            )}
            Refresh ontology
          </Button>
        </div>

        <SaveToMyFilesForm
          open={wikiSaveOpen}
          title="Save persona wiki to My files"
          defaultDirectory={wikiMyFilesTarget.directory}
          defaultFilename={wikiMyFilesTarget.filename}
          busy={savingWiki}
          onCancel={() => setWikiSaveOpen(false)}
          onConfirm={(path) => void confirmSaveWikiToMyFiles(path)}
        />

        {(wikiRunId || wikiRunPayload) && (
          <AgentRunActivity
            payload={wikiRunPayload}
            runId={wikiRunId}
            title="Persona wiki agent status"
          />
        )}

        <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
          <aside className="flex min-h-[36rem] flex-col gap-3 rounded-lg border p-3 lg:h-full">
            <div className="flex flex-wrap items-center gap-2">
              <Network className="h-4 w-4 text-primary" />
              <span className="text-sm font-medium">
                Ontology (Grab + Wiki)
              </span>
              {displayWikiOntology && (
                <>
                  <Badge variant="outline">
                    {displayWikiOntology.entities.length} entities
                  </Badge>
                  <Badge variant="outline">
                    {displayWikiOntology.keywords.length} keywords
                  </Badge>
                </>
              )}
              <label className="ml-auto flex items-center gap-1.5 text-[11px] text-muted-foreground">
                Nodes
                <Input
                  type="number"
                  min={GRAPH_MAX_NODES_MIN}
                  max={GRAPH_MAX_NODES_MAX}
                  value={graphMaxNodes}
                  onChange={(event) => {
                    const parsed = Number.parseInt(event.target.value, 10);
                    if (Number.isNaN(parsed)) return;
                    setGraphMaxNodes(
                      Math.min(
                        GRAPH_MAX_NODES_MAX,
                        Math.max(GRAPH_MAX_NODES_MIN, parsed),
                      ),
                    );
                  }}
                  className="h-7 w-16 text-xs"
                  aria-label="Maximum ontology graph nodes by weight"
                  title={`Top-N by weight (default ${DEFAULT_GRAPH_MAX_NODES}, range ${GRAPH_MAX_NODES_MIN}–${GRAPH_MAX_NODES_MAX})`}
                />
              </label>
            </div>
            {wikiOntologyNote ? (
              <p className="text-[11px] text-muted-foreground">
                {wikiOntologyNote}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Top {graphMaxNodes} nodes by fuse weight (configurable).
                Wiki-aligned entities are preferred; navigator lists the full
                fused set.
              </p>
            )}

            {ontologyLoading && !displayWikiOntology?.json_ld ? (
              <div className="flex min-h-[16rem] flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Building Grab + Wiki ontology graph…
              </div>
            ) : displayWikiOntology?.json_ld?.trim() ? (
              <div className="min-h-0 flex-1">
                <OntologyReasonGraph
                  key={`${wikiOntologyKey || ontologyKey}:${graphMaxNodes}:weight`}
                  jsonLd={displayWikiOntology.json_ld}
                  ontology={displayWikiOntology}
                  chunks={retrievedChunks.map((chunk) => ({
                    chunk_id: chunk.chunk_id,
                    parent_doc_id: chunk.parent_doc_id,
                  }))}
                  maxNodes={graphMaxNodes}
                  rankBy="weight"
                  preferredLabels={wikiPreferredLabels}
                  weights={displayWikiWeights}
                  relations={displayWikiOntology.relations}
                  fill
                  height={420}
                  title="Grab + Wiki ontology graph"
                  className="h-full min-h-[20rem]"
                />
              </div>
            ) : (
              <div className="flex min-h-[12rem] flex-1 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground">
                Run Grab &amp; generate wiki to populate the ontology graph.
              </div>
            )}

            {displayWikiOntology && (
              <OntologyNavigator
                ontology={displayWikiOntology}
                loading={ontologyLoading}
                activeChunkIds={activeChunkIds}
                activeLabel={activeLabel}
                onSelectEntity={handleSelectEntity}
                onSelectKeyword={handleSelectKeyword}
                onClearFilter={() => {
                  setActiveChunkIds(null);
                  setActiveLabel(null);
                }}
                accordionKey={`fused-nav:${wikiOntologyKey || ontologyKey}`}
              />
            )}
          </aside>

          <div className="flex min-h-[36rem] flex-col gap-3 lg:h-full">
            <ReporterChunkPanel
              chunks={retrievedChunks}
              ontology={displayWikiOntology}
              activeChunkIds={activeChunkIds}
              evidenceChunkIds={null}
              defaultOpen
              title="Grab (search) results"
              highlightChunkIds={wikiEvidenceChunkIds}
              className="min-h-0 flex-1 overflow-hidden"
            />

            <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-hidden rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-2">
                <BookOpen className="h-4 w-4 text-primary" />
                <span className="text-sm font-medium">Persona wiki</span>
                <Badge variant="outline">{persona.wikiPrompt}</Badge>
                {wikiDraft.trim() ? (
                  <Badge variant="outline">editable</Badge>
                ) : (
                  <Badge variant="outline">awaiting generate</Badge>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={savingWiki || !wikiDraft.trim() || wikiBusy}
                  onClick={() => void saveWiki()}
                >
                  {savingWiki ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4" />
                  )}
                  Store in My files
                </Button>
                {canShareToCommander && (
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    disabled={busy || savingWiki || !wikiDraft.trim()}
                    onClick={() => void sendWikiToCommander()}
                  >
                    <Send className="h-4 w-4" />
                    Send to commander
                  </Button>
                )}
                <div className="ml-auto flex gap-1">
                  <Button
                    type="button"
                    size="sm"
                    variant={wikiMode === "edit" ? "default" : "ghost"}
                    onClick={() => setWikiMode("edit")}
                  >
                    Edit
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant={wikiMode === "preview" ? "default" : "ghost"}
                    onClick={() => setWikiMode("preview")}
                  >
                    Preview
                  </Button>
                </div>
              </div>

              {wikiMode === "edit" ? (
                <textarea
                  className="min-h-0 w-full flex-1 rounded-md border bg-background px-3 py-2 font-mono text-sm"
                  value={wikiDraft}
                  onChange={(event) => {
                    setWikiDraft(event.target.value);
                    setWikiSavedPath(null);
                  }}
                  placeholder="Wiki markdown appears here after generation…"
                  disabled={wikiBusy && !wikiDraft}
                />
              ) : (
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border px-4 py-3">
                  {wikiDraft.trim() ? (
                    <MarkdownContent content={wikiDraft} />
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      No wiki content yet — run Grab &amp; generate wiki.
                    </p>
                  )}
                </div>
              )}

              {bundleDetail?.index_md && (
                <details className="shrink-0 rounded-md border px-3 py-2 text-sm">
                  <summary className="cursor-pointer font-medium">
                    Bundle index
                  </summary>
                  <div className="mt-2 max-h-40 overflow-y-auto">
                    <MarkdownContent content={bundleDetail.index_md} />
                  </div>
                </details>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
