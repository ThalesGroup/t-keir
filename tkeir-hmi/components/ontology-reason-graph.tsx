"use client";

import { memo, useEffect, useMemo, useState } from "react";
import {
  Boxes,
  CircleDot,
  Expand,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";

import { OntologyGraphCanvas } from "@/components/ontology-graph-canvas";
import { Button } from "@/components/ui/button";
import {
  applyOntologyWeights,
  buildAnalystOntologyGraph,
  jsonLdToGraph,
  markPreferredFocus,
  pruneOntologyGraph,
  type AnalystOntologyInput,
  injectOntologyRelations,
  type OntologyGraphViewMode,
  type OntologyRelationEdge,
  type OntologyWeightMaps,
} from "@/lib/ontology-graph";
import { cn } from "@/lib/utils";

interface OntologyReasonGraphProps {
  jsonLd: string | null | undefined;
  className?: string;
  width?: number;
  height?: number;
  /** Show Expand control (default true). */
  expandable?: boolean;
  title?: string;
  /** Prefer these entity/keyword labels when pruning crowded graphs. */
  preferredLabels?: string[];
  /** Cap displayed nodes. Omit (or use comprehensive) to keep the full graph. */
  maxNodes?: number;
  /** Fill parent width via flex (ignores fixed width). */
  fill?: boolean;
  /**
   * Analyst mode: never prune nodes/edges; highlight preferred labels.
   */
  comprehensive?: boolean;
  /**
   * Pruning strategy when maxNodes is set.
   * - relevance: preferred labels + degree (default)
   * - degree: highest incoming+outgoing link count
   * - weight: text-importance / fuse weights (keeps hub links)
   */
  rankBy?: "relevance" | "degree" | "weight";
  /** Node/link weights from fused ontology export. */
  weights?: OntologyWeightMaps | null;
  /**
   * Fused API relations (kg / SVO verbal predicates). Injected into the graph
   * so precise verbs appear even when JSON-LD is scaffolding-heavy.
   */
  relations?: OntologyRelationEdge[] | null;
  /**
   * Full fused ontology — preferred source for SPO display (entities + relations).
   * When set, Document/Chunk filename flood is replaced by concept SPO (or layered).
   */
  ontology?: AnalystOntologyInput | null;
  /** Retrieved chunks for Document→Chunk→concept incidence (layered mode). */
  chunks?: Array<{ chunk_id: string; parent_doc_id: string }> | null;
  /** Initial view: concepts-only SPO vs document containment hypergraph. */
  viewMode?: OntologyGraphViewMode;
}

function resolveOntologyModel(opts: {
  jsonLd: string | null | undefined;
  relations?: OntologyRelationEdge[] | null;
  ontology?: AnalystOntologyInput | null;
  chunks?: Array<{ chunk_id: string; parent_doc_id: string }> | null;
  viewMode: OntologyGraphViewMode;
  weights?: OntologyWeightMaps | null;
  preferredLabels?: string[];
  maxNodes?: number;
  comprehensive?: boolean;
  rankBy?: "relevance" | "degree" | "weight";
}) {
  const hasAnalyst =
    Boolean(opts.ontology) ||
    Boolean(opts.relations?.length) ||
    Boolean(opts.ontology?.entities?.length);

  const raw = hasAnalyst
    ? buildAnalystOntologyGraph(
        {
          ...(opts.ontology ?? {}),
          json_ld: opts.ontology?.json_ld ?? opts.jsonLd,
          relations: opts.ontology?.relations ?? opts.relations,
          chunks: opts.chunks ?? opts.ontology?.chunks,
        },
        { mode: opts.viewMode },
      )
    : injectOntologyRelations(jsonLdToGraph(opts.jsonLd), opts.relations);

  const weighted = applyOntologyWeights(raw, opts.weights);
  if (opts.comprehensive || opts.maxNodes == null) {
    return markPreferredFocus(weighted, opts.preferredLabels);
  }
  return pruneOntologyGraph(weighted, {
    preferredLabels: opts.preferredLabels,
    maxNodes: opts.maxNodes,
    rankBy: opts.rankBy,
  });
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <UserRound className="h-3 w-3 text-teal-700" /> SPO concept
      </span>
      <span className="inline-flex items-center gap-1">
        <Boxes className="h-3 w-3 text-slate-700" /> document / chunk
      </span>
      <span className="inline-flex items-center gap-1">
        <Sparkles
          className="h-3 w-3"
          style={{ color: "hsl(var(--primary))" }}
        />{" "}
        shared / focus
      </span>
      <span className="inline-flex items-center gap-1">
        <CircleDot className="h-3 w-3" /> drag · scroll zoom · double-click
        1-hop
      </span>
    </div>
  );
}

export const OntologyReasonGraph = memo(function OntologyReasonGraph({
  jsonLd,
  className,
  height = 280,
  expandable = true,
  title,
  preferredLabels,
  maxNodes,
  fill = false,
  comprehensive = false,
  rankBy = "relevance",
  weights = null,
  relations = null,
  ontology = null,
  chunks = null,
  viewMode: viewModeProp = "concepts",
}: OntologyReasonGraphProps) {
  const [expanded, setExpanded] = useState(false);
  const [viewMode, setViewMode] = useState<OntologyGraphViewMode>(viewModeProp);

  useEffect(() => {
    setViewMode(viewModeProp);
  }, [viewModeProp]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const model = useMemo(
    () =>
      resolveOntologyModel({
        jsonLd,
        relations,
        ontology,
        chunks,
        viewMode,
        weights,
        preferredLabels,
        maxNodes,
        comprehensive,
        rankBy,
      }),
    [
      jsonLd,
      preferredLabels,
      maxNodes,
      comprehensive,
      rankBy,
      weights,
      relations,
      ontology,
      chunks,
      viewMode,
    ],
  );

  const sharedCount = model.nodes.filter((node) => node.shared).length;
  const spoCount = model.edges.filter(
    (edge) => edge.label !== "contains" && edge.label !== "in",
  ).length;
  const compact = !fill && height < 400;
  const canvasHeight = Math.max(height, compact ? 280 : 360);
  const defaultLayout = viewMode === "layered" ? "tree" : "force";

  if (model.nodes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No SPO concept graph yet — run retrieval so analyzed kg relations can
        populate subject–predicate–object links.
      </p>
    );
  }

  const canvas = (
    <OntologyGraphCanvas
      key={`${viewMode}:${model.nodes.length}:${model.edges.length}`}
      model={model}
      showInspector={!compact}
      defaultLayout={defaultLayout}
      minHeight={compact ? 240 : canvasHeight}
      className="min-h-0 flex-1"
    />
  );

  return (
    <>
      <div
        className={cn(
          "flex min-h-0 flex-col overflow-hidden rounded-md border bg-muted/30",
          fill && "flex-1",
          className,
        )}
        style={
          fill
            ? { minHeight: canvasHeight }
            : { height: canvasHeight + 72 }
        }
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b px-2 py-1.5">
          <div className="min-w-0 flex-1">
            {title ? (
              <p className="mb-1 text-xs font-medium text-foreground">{title}</p>
            ) : null}
            <Legend />
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <Button
              type="button"
              size="sm"
              variant={viewMode === "concepts" ? "secondary" : "ghost"}
              className="h-7 px-2 text-[10px]"
              onClick={() => setViewMode("concepts")}
            >
              SPO concepts
            </Button>
            <Button
              type="button"
              size="sm"
              variant={viewMode === "layered" ? "secondary" : "ghost"}
              className="h-7 px-2 text-[10px]"
              onClick={() => setViewMode("layered")}
            >
              Doc → chunk → ontology
            </Button>
            {expandable && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-7 gap-1 text-xs"
                onClick={() => setExpanded(true)}
              >
                <Expand className="h-3.5 w-3.5" />
                Expand
              </Button>
            )}
          </div>
        </div>
        {canvas}
        <p className="border-t px-2 py-1 text-[10px] text-muted-foreground">
          {model.nodes.length} nodes · {spoCount} SPO links
          {viewMode === "layered"
            ? " · containment document → chunk → concepts"
            : " · filenames hidden (concept layer)"}
          {sharedCount > 0 ? ` · ${sharedCount} shared (intersection)` : ""}
          {comprehensive
            ? " · full graph (no pruning)"
            : rankBy === "weight"
              ? " · ranked by fuse weight"
              : rankBy === "degree"
                ? " · ranked by links"
                : ""}
          {" · Cytoscape: drag nodes, scroll to zoom, double-click isolates 1-hop"}
        </p>
      </div>

      {expanded ? (
        <div className="fixed inset-0 z-50 flex flex-col bg-background">
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold">
                {title || "Ontology graph"}
              </p>
              <p className="text-xs text-muted-foreground">
                Drag nodes · scroll to zoom · click to highlight neighbors ·
                double-click isolates 1-hop · Esc to close
              </p>
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              onClick={() => setExpanded(false)}
              title="Close"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
          <OntologyGraphCanvas
            key={`expanded:${viewMode}:${model.nodes.length}`}
            model={model}
            showInspector
            defaultLayout={defaultLayout}
            minHeight={480}
            className="min-h-0 flex-1"
          />
        </div>
      ) : null}
    </>
  );
});
