"use client";

import { useCallback, useMemo, useState } from "react";
import {
  AlertTriangle,
  Loader2,
  Network,
  Upload,
  X,
} from "lucide-react";

import { CorrelationIdBadge } from "@/components/correlation-id";
import { OntologyCoverageMeter } from "@/components/ontology-coverage-meter";
import { OntologyNavigator } from "@/components/ontology-navigator";
import { OntologyReasonGraph } from "@/components/ontology-reason-graph";
import { ReporterChunkCard } from "@/components/reporter-chunk-card";
import {
  SearchHeader,
  type SearchParams,
} from "@/components/search-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ontologyQueryOptions,
  parseBusinessOntologyFile,
  querySearch,
  RagApiError,
} from "@/lib/api";
import {
  chunkOntologyHaystacks,
  coverageAgainstHaystacks,
  extractBoConcepts,
  fusedOntologyHaystacks,
  type BoConceptSurface,
} from "@/lib/ontology-coverage";
import { weightMapsFromOntology } from "@/lib/ontology-graph";
import type {
  FusedOntology,
  SearchChunkHit,
  SearchResponse,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";

/** Default node budget for the left “major concepts” graph. */
const DEFAULT_GRAPH_MAX_NODES = 18;
const GRAPH_MAX_NODES_MIN = 4;
const GRAPH_MAX_NODES_MAX = 80;

type OntologyView = "global" | "query" | "merged";

interface SearchPanelProps {
  ontology: FusedOntology | null;
  ontologyLoading: boolean;
  ontologyKey: string;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onOntologyUpdate: (
    ontology: FusedOntology | null,
    meta?: { loading?: boolean; key?: string },
  ) => void;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
}

/**
 * Search workspace — retrieval only (no RAG/LLM answer).
 * Left: global (chunk-fused) / query / query⊕fuse ontology graphs · Right:
 * chunks · Bottom: ontology navigator on the global fused graph.
 * Optional external business-ontology file is sent on every /search request.
 */
export function SearchPanel({
  ontology,
  ontologyLoading,
  ontologyKey,
  activeChunkIds,
  activeLabel,
  onOntologyUpdate,
  onSelectEntity,
  onSelectKeyword,
  onClearFilter,
}: SearchPanelProps) {
  const { runtimeConfig } = useAuth();
  const defaultDataset =
    runtimeConfig?.businessOntologyDataset?.trim() || "osint";

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);

  const [boBusy, setBoBusy] = useState(false);
  const [boPayload, setBoPayload] = useState<Record<string, unknown> | null>(
    null,
  );
  const [boFilename, setBoFilename] = useState<string | null>(null);
  const [boConceptCount, setBoConceptCount] = useState(0);
  const [graphMaxNodes, setGraphMaxNodes] = useState(DEFAULT_GRAPH_MAX_NODES);
  const [ontologyView, setOntologyView] = useState<OntologyView>("global");

  const boConcepts = useMemo(
    () => extractBoConcepts(boPayload) as BoConceptSurface[],
    [boPayload],
  );

  const queryOntology = response?.query_ontology ?? null;
  const mergedOntology = response?.merged_ontology ?? null;

  const retrievedChunks = useMemo(() => {
    if (!response) return [] as SearchChunkHit[];
    const chunks = [...response.chunks];
    chunks.sort((a, b) => b.score - a.score);
    return chunks;
  }, [response]);

  const visibleChunks = useMemo(() => {
    if (!activeChunkIds || activeChunkIds.size === 0) return retrievedChunks;
    return retrievedChunks.filter((chunk) =>
      activeChunkIds.has(chunk.chunk_id),
    );
  }, [retrievedChunks, activeChunkIds]);

  const displayOntology = useMemo(() => {
    if (ontologyView === "query") return queryOntology;
    if (ontologyView === "merged") return mergedOntology ?? ontology;
    return ontology;
  }, [ontologyView, ontology, queryOntology, mergedOntology]);

  const displayWeights = useMemo(
    () => weightMapsFromOntology(displayOntology),
    [displayOntology],
  );

  const preferredLabels = useMemo(() => {
    if (!displayOntology) return [] as string[];
    const ranked = [
      ...displayOntology.entities.map((entity) => ({
        label: entity.label,
        weight:
          entity.weight ?? Math.max(1, entity.chunk_ids?.length ?? 0) * 10,
      })),
      ...displayOntology.keywords.map((keyword) => ({
        label: keyword.label,
        weight:
          keyword.weight ?? Math.max(1, keyword.chunk_ids?.length ?? 0) * 8,
      })),
    ]
      .filter((row) => row.label.trim())
      .sort((a, b) => b.weight - a.weight);
    return ranked.slice(0, 12).map((row) => row.label);
  }, [displayOntology]);

  const fusedCoverage = useMemo(
    () =>
      coverageAgainstHaystacks(
        boConcepts,
        fusedOntologyHaystacks(ontology),
      ),
    [boConcepts, ontology],
  );

  const chunkCoverageById = useMemo(() => {
    const map = new Map<string, ReturnType<typeof coverageAgainstHaystacks>>();
    if (boConcepts.length === 0) return map;
    for (const chunk of retrievedChunks) {
      map.set(
        chunk.chunk_id,
        coverageAgainstHaystacks(
          boConcepts,
          chunkOntologyHaystacks(chunk, ontology),
        ),
      );
    }
    return map;
  }, [boConcepts, ontology, retrievedChunks]);

  const handleBoUpload = useCallback(async (file: File) => {
    setBoBusy(true);
    setError(null);
    setInfo(null);
    try {
      const parsed = await parseBusinessOntologyFile(file);
      setBoPayload(parsed.business_ontology);
      setBoFilename(parsed.filename || file.name);
      setBoConceptCount(parsed.concept_count);
      setInfo(
        `Loaded business ontology “${parsed.filename || file.name}”` +
          ` (${parsed.concept_count} concepts) — sent with the next search.`,
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
  }, []);

  const handleSearch = useCallback(
    async ({ query, language, hits }: SearchParams) => {
      setLoading(true);
      setError(null);
      setInfo(null);
      setResponse(null);
      setCorrelationId(null);
      setOntologyView("global");
      onOntologyUpdate(null, { loading: true, key: query });

      try {
        const result = await querySearch({
          query,
          language,
          hits,
          ...ontologyQueryOptions(runtimeConfig),
          ...(boPayload ? { business_ontology: boPayload } : {}),
        });
        setResponse(result.response);
        setCorrelationId(result.correlationId);
        const fused = result.response.ontology ?? null;
        onOntologyUpdate(fused, { loading: false, key: query });
        const ent = fused?.entities.length ?? 0;
        const kw = fused?.keywords.length ?? 0;
        const triples = fused?.triple_count;
        const qTriples = result.response.query_ontology?.triple_count;
        const mTriples = result.response.merged_ontology?.triple_count;
        setInfo(
          `Retrieved ${result.response.documents.length} doc(s) · ` +
            `${result.response.chunks.length} chunk(s)` +
            ` · global ${ent} entities / ${kw} keywords` +
            (triples != null ? ` · ${triples} triples` : "") +
            (qTriples != null ? ` · query ${qTriples} triples` : "") +
            (mTriples != null ? ` · merged ${mTriples} triples` : "") +
            (boFilename
              ? ` · external BO “${boFilename}”`
              : ` · dataset ${defaultDataset}`),
        );
        if (boPayload) {
          const cov = coverageAgainstHaystacks(
            extractBoConcepts(boPayload),
            fusedOntologyHaystacks(fused),
          );
          if (cov.total > 0) {
            setInfo((prev) =>
              `${prev ?? ""} · BO coverage ${Math.round(cov.ratio * 100)}% (${cov.matched}/${cov.total})`.trim(),
            );
          }
        }
      } catch (caught) {
        const message =
          caught instanceof RagApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "An unexpected error occurred.";
        setError(message);
        setResponse(null);
        setCorrelationId(null);
        onOntologyUpdate(null, { loading: false, key: query });
      } finally {
        setLoading(false);
      }
    },
    [
      boFilename,
      boPayload,
      defaultDataset,
      onOntologyUpdate,
      runtimeConfig,
    ],
  );

  const viewMeta: Record<
    OntologyView,
    { label: string; title: string; blurb: string }
  > = {
    global: {
      label: "Global",
      title: "Weighted ontology hubs",
      blurb:
        "All retrieved chunk/parent ontologies fused. Nodes/links ranked by text importance (coverage + hits), summed across the fuse — hubs keep their strongest links.",
    },
    query: {
      label: "Query",
      title: "Query NLP ontology",
      blurb:
        "Linguistic pipeline on the query, extended with matched external business-ontology concepts.",
    },
    merged: {
      label: "Query ⊕ Fuse",
      title: "Query ∪ global ontology",
      blurb:
        "Union of the query ontology and the fused chunk ontology (weights summed).",
    },
  };

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary">
          Search
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">
          Retrieval &amp; ontology
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Hybrid retrieval only (no RAG answer). Left panel: global chunk
          fusion, query NLP (+ BO), and their merge. Expand a chunk for its
          analyzed ontology.
        </p>
      </div>

      <SearchHeader loading={loading} onSearch={handleSearch} />

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2">
        <label
          className={cn(
            "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm",
            (boBusy || loading) && "pointer-events-none opacity-50",
          )}
        >
          {boBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          Business ontology file
          <input
            type="file"
            accept=".yaml,.yml,.json,application/json,text/yaml,text/x-yaml"
            className="hidden"
            disabled={boBusy || loading}
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
                setInfo(null);
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">
            Sent as <code>business_ontology</code> on search — otherwise dataset{" "}
            <code>{defaultDataset}</code>
          </span>
        )}
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Search</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {info && (
        <Alert>
          <Network className="h-4 w-4" />
          <AlertTitle>Retrieval</AlertTitle>
          <AlertDescription>{info}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <aside className="flex min-h-[28rem] flex-col gap-3 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Network className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">Ontology</span>
            <div className="flex flex-wrap gap-1">
              {(Object.keys(viewMeta) as OntologyView[]).map((view) => (
                <button
                  key={view}
                  type="button"
                  onClick={() => setOntologyView(view)}
                  className={cn(
                    "rounded-md border px-2 py-0.5 text-[11px]",
                    ontologyView === view
                      ? "border-primary bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {viewMeta[view].label}
                </button>
              ))}
            </div>
            {displayOntology && (
              <>
                <Badge variant="outline">
                  {displayOntology.entities.length} entities
                </Badge>
                <Badge variant="outline">
                  {displayOntology.keywords.length} keywords
                </Badge>
                {displayOntology.triple_count != null && (
                  <Badge variant="outline">
                    {displayOntology.triple_count} triples
                  </Badge>
                )}
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
                aria-label="Maximum ontology graph nodes"
                title={`Default ${DEFAULT_GRAPH_MAX_NODES} (range ${GRAPH_MAX_NODES_MIN}–${GRAPH_MAX_NODES_MAX})`}
              />
            </label>
          </div>
          <p className="text-[11px] text-muted-foreground">
            {viewMeta[ontologyView].blurb}
          </p>

          {boConcepts.length > 0 ? (
            ontology ? (
              <OntologyCoverageMeter
                coverage={fusedCoverage}
                title="External BO ↔ global (chunk) ontology"
                showDetails
              />
            ) : (
              <p className="text-[11px] text-muted-foreground">
                External BO loaded ({boConcepts.length} concepts) — run search
                to measure coverage against the fused graph.
              </p>
            )
          ) : (
            <p className="text-[11px] text-muted-foreground">
              Upload a business ontology file to measure coverage of the
              extended request against this graph and each chunk.
            </p>
          )}

          {ontologyLoading && !displayOntology?.json_ld ? (
            <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Building query / fused ontologies…
            </div>
          ) : displayOntology?.json_ld?.trim() &&
            displayOntology.json_ld.trim() !== "[]" ? (
            <OntologyReasonGraph
              key={`${ontologyKey}:${ontologyView}:${graphMaxNodes}:weight`}
              jsonLd={displayOntology.json_ld}
              ontology={displayOntology}
              chunks={retrievedChunks.map((chunk) => ({
                chunk_id: chunk.chunk_id,
                parent_doc_id: chunk.parent_doc_id,
              }))}
              maxNodes={graphMaxNodes}
              rankBy="weight"
              preferredLabels={preferredLabels}
              weights={displayWeights}
              relations={displayOntology.relations}
              fill
              height={420}
              title={viewMeta[ontologyView].title}
              className="flex-1"
            />
          ) : (
            <div className="flex flex-1 items-center justify-center rounded-md border border-dashed px-4 text-center text-sm text-muted-foreground">
              {response
                ? `No ${viewMeta[ontologyView].label.toLowerCase()} ontology graph for this query.`
                : "Run a search to display the ontology graph."}
            </div>
          )}
        </aside>

        <div className="min-h-[28rem] space-y-3 rounded-lg border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Retrieved chunks</span>
            {response && (
              <Badge variant="outline">
                {visibleChunks.length}
                {activeChunkIds && activeChunkIds.size > 0
                  ? ` / ${retrievedChunks.length} filtered`
                  : ` / ${retrievedChunks.length}`}
              </Badge>
            )}
            {!loading && correlationId && (
              <CorrelationIdBadge correlationId={correlationId} />
            )}
          </div>

          {loading && (
            <div className="space-y-2">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          )}

          {!loading && response && visibleChunks.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {retrievedChunks.length === 0
                ? "No chunks retrieved for this query."
                : "No chunks match the current ontology filter."}
            </p>
          )}

          {!loading && visibleChunks.length > 0 && (
            <ul className="space-y-2">
              {visibleChunks.map((chunk, index) => (
                <ReporterChunkCard
                  key={chunk.chunk_id}
                  chunk={chunk}
                  ontology={ontology}
                  active={
                    !activeChunkIds ||
                    activeChunkIds.size === 0 ||
                    activeChunkIds.has(chunk.chunk_id)
                  }
                  defaultOpen={index === 0}
                  ontologyTitle="Chunk ontology"
                  boCoverage={chunkCoverageById.get(chunk.chunk_id) ?? null}
                />
              ))}
            </ul>
          )}

          {!loading && !response && (
            <p className="text-sm text-muted-foreground">
              Submit a query to retrieve grounded passages.
            </p>
          )}
        </div>
      </div>

      <OntologyNavigator
        ontology={ontology}
        loading={ontologyLoading}
        activeChunkIds={activeChunkIds}
        activeLabel={activeLabel}
        onSelectEntity={onSelectEntity}
        onSelectKeyword={onSelectKeyword}
        onClearFilter={onClearFilter}
        accordionKey={ontologyKey}
      />
    </div>
  );
}
