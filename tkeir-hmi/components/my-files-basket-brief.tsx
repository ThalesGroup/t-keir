"use client";

import { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  FileText,
  Loader2,
  ShoppingBasket,
  Sparkles,
  Upload,
  X,
} from "lucide-react";

import { OntologyNavigator } from "@/components/ontology-navigator";
import { RagResults } from "@/components/rag-results";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  analyzeDocumentFile,
  getAnalyzedDocument,
  ontologyQueryOptions,
  parseBusinessOntologyFile,
  queryRag,
  RagApiError,
} from "@/lib/api";
import { mergeOntologyJsonLd } from "@/lib/reporter";
import type {
  FusedOntology,
  ProposedOntologyQuery,
  QueryResponse,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";
import type { RuntimeConfig } from "@/src/config/runtimeConfig";
import { useAuth } from "@/src/auth/AuthProvider";
import { apiFetch } from "@/src/auth/useApiClient";
import { cn } from "@/lib/utils";

export type BasketItem = {
  path: string;
  name: string;
  source_ref: string;
  status?: string;
  passage_count?: number;
};

export type BasketIndexOptions = {
  business_ontology?: Record<string, unknown>;
  business_ontology_dataset?: string;
};

type BasketBriefProps = {
  items: BasketItem[];
  onRemove: (path: string) => void;
  onClear: () => void;
  onIndexMissing: (
    paths: string[],
    options?: BasketIndexOptions,
  ) => Promise<void>;
  indexing?: boolean;
};

const DEFAULT_BRIEF_QUERY =
  "Synthesize a concise operational brief from these documents: key findings, actors, locations, timeline, risks, and recommended attention points.";

function basenameLabels(items: BasketItem[], limit = 4): string {
  const names = items.map((item) => item.name.replace(/\.(md|markdown)$/i, ""));
  if (names.length <= limit) return names.join(", ");
  return `${names.slice(0, limit).join(", ")} (+${names.length - limit} more)`;
}

/** Basket-adapted chips for quick re-query (RAG brief, not OWL expressions). */
export function buildBasketBriefQueries(
  items: BasketItem[],
): ProposedOntologyQuery[] {
  const labels = basenameLabels(items, 3);
  return [
    {
      kind: "expression",
      title: "Operational brief",
      query: DEFAULT_BRIEF_QUERY,
      description: `Grounded on basket: ${labels}`,
    },
    {
      kind: "expression",
      title: "Actors & orgs",
      query: `Who are the main actors, organizations, and units mentioned across: ${labels}? What relationships connect them?`,
      description: "Entity focus across selected documents",
    },
    {
      kind: "expression",
      title: "Timeline",
      query: `Reconstruct the chronological timeline of events reported in: ${labels}. Cite dates and locations.`,
      description: "Temporal reconstruction",
    },
    {
      kind: "expression",
      title: "Threats & risks",
      query: `What threats, risks, anomalies, or indicators are described in: ${labels}? Prioritize by severity.`,
      description: "Risk-oriented brief",
    },
    {
      kind: "expression",
      title: "Locations",
      query: `List geographic locations and areas of interest referenced in: ${labels}, and how they relate.`,
      description: "Geospatial focus",
    },
  ];
}

async function analyzeWorkspacePathForOntology(
  item: BasketItem,
  boPayload: Record<string, unknown> | null,
): Promise<string | null> {
  const res = await apiFetch(
    `/api/ingest/workspace/file?path=${encodeURIComponent(item.path)}`,
    { cache: "no-store" },
  );
  if (!res.ok) return null;
  const body = (await res.json()) as { content?: string; name?: string };
  const content = body.content ?? "";
  if (!content.trim()) return null;
  const boFile = boPayload
    ? new Blob([JSON.stringify(boPayload)], { type: "application/json" })
    : undefined;
  const analyzed = await analyzeDocumentFile({
    file: new Blob([content], { type: "text/markdown" }),
    filename: body.name || item.name,
    businessOntologyFile: boFile,
    businessOntologyFilename: "business_ontology.json",
  });
  const ld = analyzed.document_ontology?.json_ld;
  return typeof ld === "string" && ld.trim() ? ld : null;
}

async function collectBasketOntologyJsonLd(
  items: BasketItem[],
  runtimeConfig: RuntimeConfig | null | undefined,
  boPayload: Record<string, unknown> | null,
): Promise<{
  jsonLd?: string;
  loaded: number;
  analyzedLive: number;
  missing: string[];
}> {
  const parts: string[] = [];
  const missing: string[] = [];
  let analyzedLive = 0;
  for (const item of items) {
    const ref = item.source_ref;
    try {
      const doc = await getAnalyzedDocument(ref, runtimeConfig);
      const ld = doc.document_ontology?.json_ld;
      if (typeof ld === "string" && ld.trim()) {
        parts.push(ld);
        continue;
      }
    } catch {
      // fall through to live NLP
    }
    try {
      const liveLd = await analyzeWorkspacePathForOntology(item, boPayload);
      if (liveLd) {
        parts.push(liveLd);
        analyzedLive += 1;
        continue;
      }
    } catch {
      // record missing
    }
    missing.push(ref);
  }
  return {
    jsonLd: mergeOntologyJsonLd(parts),
    loaded: parts.length,
    analyzedLive,
    missing,
  };
}

export function MyFilesBasketBrief({
  items,
  onRemove,
  onClear,
  onIndexMissing,
  indexing = false,
}: BasketBriefProps) {
  const { runtimeConfig } = useAuth();
  const defaultDataset =
    runtimeConfig?.businessOntologyDataset?.trim() || "osint";
  const [query, setQuery] = useState(DEFAULT_BRIEF_QUERY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [ontology, setOntology] = useState<FusedOntology | null>(null);
  const [ontologyLoading, setOntologyLoading] = useState(false);
  const [activeChunkIds, setActiveChunkIds] = useState<Set<string> | null>(
    null,
  );
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [boPayload, setBoPayload] = useState<Record<string, unknown> | null>(
    null,
  );
  const [boFilename, setBoFilename] = useState<string | null>(null);
  const [boConceptCount, setBoConceptCount] = useState(0);
  const [boBusy, setBoBusy] = useState(false);

  const notIndexed = useMemo(
    () =>
      items.filter(
        (item) =>
          item.status !== "indexed" ||
          !item.source_ref ||
          (typeof item.passage_count === "number" && item.passage_count <= 0),
      ),
    [items],
  );

  const readyItems = useMemo(
    () =>
      items.filter(
        (item) =>
          item.status === "indexed" &&
          item.source_ref &&
          (item.passage_count === undefined || item.passage_count > 0),
      ),
    [items],
  );

  const readyRefs = useMemo(
    () => readyItems.map((item) => item.source_ref),
    [readyItems],
  );

  const proposedChips = useMemo(
    () => buildBasketBriefQueries(items),
    [items],
  );

  const indexOptions = useCallback((): BasketIndexOptions => {
    const options: BasketIndexOptions = {
      business_ontology_dataset: defaultDataset,
    };
    if (boPayload) options.business_ontology = boPayload;
    return options;
  }, [boPayload, defaultDataset]);

  async function handleBoUpload(file: File) {
    setBoBusy(true);
    setError(null);
    try {
      const parsed = await parseBusinessOntologyFile(file);
      setBoPayload(parsed.business_ontology);
      setBoFilename(parsed.filename || file.name);
      setBoConceptCount(parsed.concept_count);
      setInfo(
        `Loaded business ontology “${parsed.filename || file.name}”` +
          ` (${parsed.concept_count} concepts). It will be merged into brief` +
          ` fusion and used when indexing basket docs.`,
      );
    } catch (caught) {
      setBoPayload(null);
      setBoFilename(null);
      setBoConceptCount(0);
      setError(
        caught instanceof RagApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Failed to parse business ontology file",
      );
    } finally {
      setBoBusy(false);
    }
  }

  const runBrief = useCallback(
    async (overrideQuery?: string) => {
      const q = (overrideQuery ?? query).trim();
      if (!q || readyRefs.length === 0) return;
      setLoading(true);
      setOntologyLoading(true);
      setError(null);
      setInfo(null);
      setResponse(null);
      setCorrelationId(null);
      setSubmittedQuery(q);
      setActiveChunkIds(null);
      setActiveLabel(null);
      if (overrideQuery) setQuery(overrideQuery);

      try {
        // Existing analyzed dumps first; otherwise run NLP on workspace files.
        const ontologyBundle = await collectBasketOntologyJsonLd(
          readyItems,
          runtimeConfig,
          boPayload,
        );
        if (ontologyBundle.missing.length > 0) {
          const missingPaths = readyItems
            .filter((item) => ontologyBundle.missing.includes(item.source_ref))
            .map((item) => item.path);
          if (missingPaths.length > 0) {
            setInfo(
              `Could not load ontology for ${missingPaths.length} doc(s) —` +
                ` queuing NLP + index with business ontology in background.`,
            );
            void onIndexMissing(missingPaths, indexOptions());
          }
        }

        const result = await queryRag({
          query: q,
          language: "en",
          hits: Math.min(40, Math.max(20, readyRefs.length * 6)),
          search_mode: "user",
          source_refs: readyRefs,
          ontology_json_ld: ontologyBundle.jsonLd,
          ...(boPayload ? { business_ontology: boPayload } : {}),
          ...ontologyQueryOptions(runtimeConfig),
        });
        setResponse(result.response);
        setCorrelationId(result.correlationId);
        setOntology(result.response.ontology ?? null);
        const ent = result.response.ontology?.entities.length ?? 0;
        const kw = result.response.ontology?.keywords.length ?? 0;
        setInfo(
          `Brief ready · ontology ${ent} entities / ${kw} keywords` +
            ` · fused from ${ontologyBundle.loaded}/${readyRefs.length} doc(s)` +
            (ontologyBundle.analyzedLive
              ? ` (${ontologyBundle.analyzedLive} live NLP)`
              : "") +
            (boFilename
              ? ` · BO file “${boFilename}” (${boConceptCount} concepts)`
              : ` · BO dataset ${defaultDataset}`),
        );
      } catch (caught) {
        const message =
          caught instanceof RagApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "Brief generation failed.";
        setError(message);
        setOntology(null);
      } finally {
        setLoading(false);
        setOntologyLoading(false);
      }
    },
    [
      query,
      readyRefs,
      readyItems,
      runtimeConfig,
      boPayload,
      boFilename,
      boConceptCount,
      defaultDataset,
      onIndexMissing,
      indexOptions,
    ],
  );

  const handleSelectEntity = useCallback(
    (entity: SemanticEntity) => {
      setActiveChunkIds((prev) => {
        if (prev && activeLabel === entity.label) {
          setActiveLabel(null);
          return null;
        }
        setActiveLabel(entity.label);
        return new Set(entity.chunk_ids);
      });
    },
    [activeLabel],
  );

  const handleSelectKeyword = useCallback(
    (keyword: SemanticKeyword) => {
      setActiveChunkIds((prev) => {
        if (prev && activeLabel === keyword.label) {
          setActiveLabel(null);
          return null;
        }
        setActiveLabel(keyword.label);
        return new Set(keyword.chunk_ids);
      });
    },
    [activeLabel],
  );

  if (items.length === 0) return null;

  return (
    <div className="space-y-4 rounded-xl border bg-card/40 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <ShoppingBasket className="h-3.5 w-3.5" />
            Document basket
          </p>
          <h3 className="mt-1 text-lg font-semibold tracking-tight">
            Brief from selection
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Fuse NLP analyzed ontologies (+ optional uploaded business
            ontology), then RAG-generate a brief. Same Brief + Ontology
            navigator as Search.
          </p>
        </div>
        <Button type="button" size="sm" variant="ghost" onClick={onClear}>
          Clear basket
        </Button>
      </div>

      <ul className="flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item.path}>
            <Badge
              variant="outline"
              className={cn(
                "gap-1.5 py-1 pl-2 pr-1",
                item.status === "indexed"
                  ? "border-emerald-500/40"
                  : "border-amber-500/40",
              )}
            >
              <FileText className="h-3 w-3 shrink-0" />
              <span className="max-w-[12rem] truncate" title={item.path}>
                {item.name}
              </span>
              <button
                type="button"
                className="rounded p-0.5 hover:bg-muted"
                aria-label={`Remove ${item.name}`}
                onClick={() => onRemove(item.path)}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2">
        <label
          className={cn(
            "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm",
            (boBusy || loading || indexing) && "pointer-events-none opacity-50",
          )}
        >
          {boBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          Business ontology
          <input
            type="file"
            accept=".yaml,.yml,.json,application/json,text/yaml,text/x-yaml"
            className="hidden"
            disabled={boBusy || loading || indexing}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleBoUpload(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
        {boFilename ? (
          <Badge variant="outline" className="gap-1.5">
            {boFilename}
            <span className="text-muted-foreground">
              ({boConceptCount} concepts)
            </span>
            <button
              type="button"
              className="rounded p-0.5 hover:bg-muted"
              aria-label="Clear business ontology file"
              onClick={() => {
                setBoPayload(null);
                setBoFilename(null);
                setBoConceptCount(0);
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">
            Optional upload — otherwise uses dataset{" "}
            <code>{defaultDataset}</code>
          </span>
        )}
      </div>

      {notIndexed.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>
            {notIndexed.length} document(s) need indexing
          </AlertTitle>
          <AlertDescription className="flex flex-wrap items-center gap-2">
            Index runs the NLP pipeline (with business ontology annotation) and
            writes analyzed dumps used for fused ontology.
            <Button
              type="button"
              size="sm"
              variant="secondary"
              disabled={indexing || loading}
              onClick={() =>
                void onIndexMissing(
                  notIndexed.map((item) => item.path),
                  indexOptions(),
                )
              }
            >
              {indexing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              Index basket docs
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        {proposedChips.map((chip) => (
          <Button
            key={chip.title}
            type="button"
            size="sm"
            variant="outline"
            disabled={loading || readyRefs.length === 0}
            title={chip.description || chip.query}
            onClick={() => void runBrief(chip.query)}
          >
            {chip.title}
          </Button>
        ))}
      </div>

      <div className="flex flex-col gap-2 sm:flex-row">
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Brief question over basket documents…"
          disabled={loading}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void runBrief();
            }
          }}
        />
        <Button
          type="button"
          disabled={loading || readyRefs.length === 0 || !query.trim()}
          onClick={() => void runBrief()}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          Generate brief
        </Button>
      </div>

      {readyRefs.length === 0 && (
        <p className="text-xs text-muted-foreground">
          Add indexed documents (with passages) to enable brief generation.
        </p>
      )}

      {info && (
        <Alert>
          <Sparkles className="h-4 w-4" />
          <AlertTitle>Basket brief</AlertTitle>
          <AlertDescription>{info}</AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Brief failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {(loading || response) && (
        <div className="space-y-6 border-t pt-4">
          <RagResults
            submittedQuery={submittedQuery}
            response={response}
            correlationId={correlationId}
            loading={loading}
            activeChunkIds={activeChunkIds}
          />
          <OntologyNavigator
            ontology={ontology}
            loading={ontologyLoading}
            activeChunkIds={activeChunkIds}
            activeLabel={activeLabel}
            onSelectEntity={handleSelectEntity}
            onSelectKeyword={handleSelectKeyword}
            onClearFilter={() => {
              setActiveChunkIds(null);
              setActiveLabel(null);
            }}
            accordionKey={`basket-${submittedQuery || "idle"}`}
          />
        </div>
      )}
    </div>
  );
}
