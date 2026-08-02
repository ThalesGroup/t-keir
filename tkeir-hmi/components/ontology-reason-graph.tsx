"use client";

import {
  memo,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import {
  Boxes,
  CircleDot,
  Expand,
  Minus,
  Plus,
  Quote,
  RotateCcw,
  Search,
  Sparkles,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  applyOntologyWeights,
  buildAnalystOntologyGraph,
  jsonLdToGraph,
  layoutOntologyGraph,
  markPreferredFocus,
  pruneOntologyGraph,
  type AnalystOntologyInput,
  type LaidOutNode,
  type OntologyGraphEdge,
  injectOntologyRelations,
  type OntologyGraphNode,
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
  /** Fill parent width via ResizeObserver (ignores fixed width). */
  fill?: boolean;
  /**
   * Analyst mode: never prune nodes/edges; scale canvas; highlight preferred
   * labels; use spacious layout with prominent directed arrows.
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

function kindIcon(kind: OntologyGraphNode["kind"]): LucideIcon {
  switch (kind) {
    case "class":
      return Boxes;
    case "individual":
      return UserRound;
    case "literal":
      return Quote;
    case "result":
      return CircleDot;
    case "document":
      return Boxes;
    case "chunk":
      return CircleDot;
    default:
      return Sparkles;
  }
}

function nodeFill(kind: OntologyGraphNode["kind"], focus?: boolean): string {
  if (focus) {
    return "hsl(var(--primary))";
  }
  switch (kind) {
    case "class":
      return "#4338ca";
    case "individual":
      return "#0f766e";
    case "literal":
      return "#a16207";
    case "result":
      return "#64748b";
    case "document":
      return "#1e3a5f";
    case "chunk":
      return "#475569";
    default:
      return "#475569";
  }
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

function GraphSvg({
  nodes,
  edges,
  width,
  height,
  markerId,
  selectedId,
  neighborIds,
  onSelect,
  labelMax = 18,
  fontSize = 10,
  arrowScale = 1,
}: {
  nodes: LaidOutNode[];
  edges: OntologyGraphEdge[];
  width: number;
  height: number;
  markerId: string;
  selectedId: string | null;
  neighborIds: Set<string>;
  onSelect?: (id: string) => void;
  labelMax?: number;
  fontSize?: number;
  arrowScale?: number;
}) {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const markerW = 6 * arrowScale;
  const markerH = 6 * arrowScale;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Ontology graph"
      className="select-none"
    >
      <defs>
        <marker
          id={markerId}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth={markerW}
          markerHeight={markerH}
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="#334155" />
        </marker>
        <marker
          id={`${markerId}-active`}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth={markerW * 1.15}
          markerHeight={markerH * 1.15}
          markerUnits="userSpaceOnUse"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill="hsl(var(--primary))" />
        </marker>
      </defs>
      {edges.map((edge) => {
        const source = byId.get(edge.source);
        const target = byId.get(edge.target);
        if (!source || !target) return null;
        const related =
          !selectedId ||
          edge.source === selectedId ||
          edge.target === selectedId;
        // Shorten line so arrowheads sit on the node border, not the center.
        const dx = target.x - source.x;
        const dy = target.y - source.y;
        const len = Math.hypot(dx, dy) || 1;
        const pad = 20;
        const x1 = source.x + (dx / len) * pad;
        const y1 = source.y + (dy / len) * pad;
        const x2 = target.x - (dx / len) * (pad + 2);
        const y2 = target.y - (dy / len) * (pad + 2);
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const active = Boolean(selectedId && related);
        const edgeWeight = Math.max(1, edge.weight ?? 1);
        const strokeBase = Math.min(4.5, 1.2 + Math.log2(edgeWeight + 1) * 0.9);
        const weightLabel =
          edge.weight != null && edge.weight > 1
            ? ` ×${Number.isInteger(edge.weight) ? edge.weight : edge.weight.toFixed(1)}`
            : "";
        const edgeCaption = `${edge.label || ""}${weightLabel}`;
        return (
          <g key={edge.id} opacity={related ? 1 : 0.12}>
            <line
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={active ? "hsl(var(--primary))" : "#475569"}
              strokeWidth={
                (active ? strokeBase + 0.6 : strokeBase) * arrowScale
              }
              markerEnd={`url(#${active ? `${markerId}-active` : markerId})`}
            />
            {edgeCaption ? (
              <g transform={`translate(${mx}, ${my})`}>
                <rect
                  x={-Math.min(58, edgeCaption.length * 3.4 + 8)}
                  y={-10}
                  width={Math.min(116, edgeCaption.length * 6.8 + 16)}
                  height={16}
                  rx={4}
                  fill="hsl(var(--background))"
                  stroke={active ? "hsl(var(--primary))" : "#cbd5e1"}
                  strokeWidth={0.75}
                  opacity={0.95}
                />
                <text
                  y={2}
                  textAnchor="middle"
                  className="fill-foreground"
                  style={{ fontSize: Math.max(8, fontSize - 1), fontWeight: 500 }}
                >
                  {edgeCaption.length > 18
                    ? `${edgeCaption.slice(0, 17)}…`
                    : edgeCaption}
                </text>
              </g>
            ) : null}
          </g>
        );
      })}
      {nodes.map((node) => {
        const selected = node.id === selectedId;
        const neighbor = neighborIds.has(node.id);
        const dimmed = Boolean(selectedId) && !selected && !neighbor;
        const full = node.label;
        const label =
          full.length > labelMax ? `${full.slice(0, labelMax - 1)}…` : full;
        const Icon = kindIcon(node.kind);
        const nodeWeight = Math.max(0, node.weight ?? 0);
        const weightBoost = Math.min(28, Math.log2(nodeWeight + 1) * 8);
        const w = Math.max(
          78,
          Math.min(
            selected ? 176 : 150,
            label.length * (fontSize * 0.7) + 36 + weightBoost,
          ),
        );
        const h = (selected ? 36 : 30) + Math.min(10, weightBoost * 0.35);
        const weightHint =
          node.weight != null && node.weight > 0
            ? ` · weight ${node.weight.toFixed(1)}`
            : "";
        return (
          <g
            key={node.id}
            transform={`translate(${node.x}, ${node.y})`}
            opacity={dimmed ? 0.2 : 0.95}
            style={{ cursor: onSelect ? "pointer" : "default" }}
            onClick={(event) => {
              event.stopPropagation();
              onSelect?.(node.id);
            }}
          >
            <title>{`${node.label} (${node.kind}${weightHint})\n${node.id}`}</title>
            <rect
              x={-w / 2}
              y={-h / 2}
              width={w}
              height={h}
              rx={8}
              fill={nodeFill(node.kind, node.focus || node.shared || selected)}
              stroke={
                selected || node.focus || node.shared ? "#f8fafc" : "transparent"
              }
              strokeWidth={selected || node.focus || node.shared ? 2 : 0}
            />
            <foreignObject
              x={-w / 2 + 6}
              y={-7}
              width={14}
              height={14}
            >
              <div
                // foreignObject host for Lucide icons inside SVG
                className="flex h-full w-full items-center justify-center text-white"
              >
                <Icon className="h-3.5 w-3.5" strokeWidth={2.4} aria-hidden />
              </div>
            </foreignObject>
            <text
              x={-w / 2 + 24}
              textAnchor="start"
              dominantBaseline="central"
              fill="#f8fafc"
              style={{ fontSize, fontWeight: 600 }}
            >
              {label}
            </text>
          </g>
        );
      })}
    </svg>
  );
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
        shared (intersection) / focus
      </span>
      <span className="inline-flex items-center gap-1 text-muted-foreground/80">
        → predicate links
      </span>
    </div>
  );
}

function ExpandedExplorer({
  jsonLd,
  title,
  preferredLabels,
  maxNodes,
  comprehensive,
  rankBy,
  weights,
  relations,
  ontology,
  chunks,
  viewMode,
  onClose,
}: {
  jsonLd: string;
  title?: string;
  preferredLabels?: string[];
  maxNodes?: number;
  comprehensive?: boolean;
  rankBy?: "relevance" | "degree" | "weight";
  weights?: OntologyWeightMaps | null;
  relations?: OntologyRelationEdge[] | null;
  ontology?: AnalystOntologyInput | null;
  chunks?: Array<{ chunk_id: string; parent_doc_id: string }> | null;
  viewMode: OntologyGraphViewMode;
  onClose: () => void;
}) {
  const markerId = useId().replace(/:/g, "");
  const viewportRef = useRef<HTMLDivElement>(null);
  const [viewport, setViewport] = useState({ w: 900, h: 640 });
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragOrigin = useRef<{ x: number; y: number; panX: number; panY: number } | null>(
    null,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

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

  const canvasW = Math.max(
    900,
    viewport.w * 1.4,
    comprehensive ? 420 + Math.sqrt(model.nodes.length) * 55 : 0,
  );
  const canvasH = Math.max(
    700,
    viewport.h * 1.4,
    comprehensive ? 380 + Math.sqrt(model.nodes.length) * 50 : 0,
  );

  const laidOut = useMemo(
    () =>
      layoutOntologyGraph(model, canvasW, canvasH, {
        spacious: comprehensive,
        layered: viewMode === "layered",
      }),
    [model, canvasW, canvasH, comprehensive, viewMode],
  );

  const neighborIds = useMemo(() => {
    const set = new Set<string>();
    if (!selectedId) return set;
    set.add(selectedId);
    for (const edge of laidOut.edges) {
      if (edge.source === selectedId) set.add(edge.target);
      if (edge.target === selectedId) set.add(edge.source);
    }
    return set;
  }, [laidOut.edges, selectedId]);

  const selectedNode = useMemo(
    () => laidOut.nodes.find((node) => node.id === selectedId) || null,
    [laidOut.nodes, selectedId],
  );

  const filteredNodes = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return laidOut.nodes;
    return laidOut.nodes.filter(
      (node) =>
        node.label.toLowerCase().includes(q) ||
        node.id.toLowerCase().includes(q) ||
        node.kind.toLowerCase().includes(q),
    );
  }, [filter, laidOut.nodes]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const measure = () => {
      setViewport({
        w: el.clientWidth || 900,
        h: el.clientHeight || 640,
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const centerOnNode = useCallback(
    (node: LaidOutNode) => {
      setSelectedId(node.id);
      const nextScale = Math.max(scale, 1.15);
      setScale(nextScale);
      setPan({
        x: viewport.w / 2 - node.x * nextScale,
        y: viewport.h / 2 - node.y * nextScale,
      });
    },
    [scale, viewport.h, viewport.w],
  );

  const onWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY > 0 ? 0.9 : 1.1;
    setScale((prev) => Math.min(4, Math.max(0.35, prev * delta)));
  };

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    setDragging(true);
    dragOrigin.current = {
      x: event.clientX,
      y: event.clientY,
      panX: pan.x,
      panY: pan.y,
    };
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging || !dragOrigin.current) return;
    setPan({
      x: dragOrigin.current.panX + (event.clientX - dragOrigin.current.x),
      y: dragOrigin.current.panY + (event.clientY - dragOrigin.current.y),
    });
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    setDragging(false);
    dragOrigin.current = null;
    try {
      (event.currentTarget as HTMLElement).releasePointerCapture(
        event.pointerId,
      );
    } catch {
      // ignore
    }
  };

  const resetView = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
    setSelectedId(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold">
            {title || "Ontology graph"}
          </p>
          <p className="text-xs text-muted-foreground">
            Drag to pan · scroll to zoom · click a node or list item to focus
            neighbors · Esc to close
          </p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="outline"
            onClick={() => setScale((s) => Math.max(0.35, s * 0.85))}
            title="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">
            {Math.round(scale * 100)}%
          </span>
          <Button
            type="button"
            size="icon"
            variant="outline"
            onClick={() => setScale((s) => Math.min(4, s * 1.15))}
            title="Zoom in"
          >
            <Plus className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            onClick={resetView}
            title="Reset view"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={onClose}
            title="Close"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-72 shrink-0 flex-col border-r bg-card/60">
          <div className="space-y-2 border-b p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={filter}
                onChange={(event) => setFilter(event.target.value)}
                placeholder="Filter nodes…"
                className="h-8 pl-8 text-xs"
              />
            </div>
            <p className="text-[11px] text-muted-foreground">
              {laidOut.nodes.length} nodes · {laidOut.edges.length} edges
            </p>
            <Legend />
          </div>
          <ul className="flex-1 space-y-0.5 overflow-y-auto p-2">
            {filteredNodes.map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  className={cn(
                    "flex w-full flex-col rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted",
                    selectedId === node.id && "bg-primary/10 text-primary",
                  )}
                  onClick={() => centerOnNode(node)}
                >
                  <span className="flex items-center gap-1.5 truncate font-medium">
                    {(() => {
                      const Icon = kindIcon(node.kind);
                      return <Icon className="h-3 w-3 shrink-0" />;
                    })()}
                    {node.label}
                  </span>
                  <span className="truncate font-mono text-[10px] text-muted-foreground">
                    {node.kind} · {node.id}
                  </span>
                </button>
              </li>
            ))}
            {filteredNodes.length === 0 && (
              <li className="px-2 py-4 text-xs text-muted-foreground">
                No nodes match the filter.
              </li>
            )}
          </ul>
          {selectedNode && (
            <div className="space-y-1 border-t p-3 text-xs">
              <p className="font-medium">{selectedNode.label}</p>
              <Badge variant="outline">{selectedNode.kind}</Badge>
              <p className="break-all font-mono text-[10px] text-muted-foreground">
                {selectedNode.id}
              </p>
              <p className="text-muted-foreground">
                {Math.max(0, neighborIds.size - 1)} neighbor(s) highlighted
              </p>
            </div>
          )}
        </aside>

        <div
          ref={viewportRef}
          className={cn(
            "relative min-w-0 flex-1 overflow-hidden bg-muted/20",
            dragging ? "cursor-grabbing" : "cursor-grab",
          )}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onClick={() => setSelectedId(null)}
        >
          <div
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
              transformOrigin: "0 0",
              width: canvasW,
              height: canvasH,
            }}
          >
            <GraphSvg
              nodes={laidOut.nodes}
              edges={laidOut.edges}
              width={canvasW}
              height={canvasH}
              markerId={`${markerId}-expanded`}
              selectedId={selectedId}
              neighborIds={neighborIds}
              onSelect={(id) => {
                const node = laidOut.nodes.find((item) => item.id === id);
                if (node) centerOnNode(node);
              }}
              labelMax={28}
              fontSize={12}
              arrowScale={comprehensive ? 1.35 : 1.15}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export const OntologyReasonGraph = memo(function OntologyReasonGraph({
  jsonLd,
  className,
  width = 360,
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
  const markerId = useId().replace(/:/g, "");
  const hostRef = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hostWidth, setHostWidth] = useState(width);
  const [viewMode, setViewMode] = useState<OntologyGraphViewMode>(viewModeProp);

  useEffect(() => {
    setViewMode(viewModeProp);
  }, [viewModeProp]);

  useEffect(() => {
    if (!fill) {
      setHostWidth(width);
      return;
    }
    const el = hostRef.current;
    if (!el) return;
    const measure = () => setHostWidth(Math.max(280, el.clientWidth || width));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [fill, width]);

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

  const graphWidth = Math.max(
    fill ? hostWidth : width,
    comprehensive ? 320 + Math.min(280, Math.sqrt(model.nodes.length) * 28) : 0,
  );
  const graphHeight = Math.max(
    height,
    comprehensive
      ? Math.min(720, 360 + Math.sqrt(Math.max(model.nodes.length, 1)) * 42)
      : height,
  );

  const laidOut = useMemo(
    () =>
      layoutOntologyGraph(model, graphWidth, graphHeight, {
        spacious: comprehensive,
        layered: viewMode === "layered",
      }),
    [model, graphWidth, graphHeight, comprehensive, viewMode],
  );

  const neighborIds = useMemo(() => {
    const set = new Set<string>();
    if (!selectedId) return set;
    set.add(selectedId);
    for (const edge of laidOut.edges) {
      if (edge.source === selectedId) set.add(edge.target);
      if (edge.target === selectedId) set.add(edge.source);
    }
    return set;
  }, [laidOut.edges, selectedId]);

  const sharedCount = model.nodes.filter((node) => node.shared).length;
  const spoCount = model.edges.filter(
    (edge) => edge.label !== "contains" && edge.label !== "in",
  ).length;

  if (laidOut.nodes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No SPO concept graph yet — run retrieval so analyzed kg relations can
        populate subject–predicate–object links.
      </p>
    );
  }

  return (
    <>
      <div
        ref={hostRef}
        className={cn(
          "overflow-hidden rounded-md border bg-muted/30",
          className,
        )}
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
        <div className="max-h-[42rem] overflow-auto">
          <GraphSvg
            nodes={laidOut.nodes}
            edges={laidOut.edges}
            width={graphWidth}
            height={graphHeight}
            markerId={`${markerId}-compact`}
            selectedId={selectedId}
            neighborIds={neighborIds}
            onSelect={(id) =>
              setSelectedId((prev) => (prev === id ? null : id))
            }
            arrowScale={comprehensive ? 1.3 : 1}
          />
        </div>
        <p className="border-t px-2 py-1 text-[10px] text-muted-foreground">
          {laidOut.nodes.length} nodes · {spoCount} SPO links
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
          {expandable ? " · Expand for pan/zoom" : ""}.
        </p>
      </div>

      {expanded && (jsonLd?.trim() || ontology) && (
        <ExpandedExplorer
          jsonLd={jsonLd || "[]"}
          title={title}
          preferredLabels={preferredLabels}
          maxNodes={comprehensive ? undefined : maxNodes}
          comprehensive={comprehensive}
          rankBy={rankBy}
          weights={weights}
          relations={relations}
          ontology={ontology}
          chunks={chunks}
          viewMode={viewMode}
          onClose={() => setExpanded(false)}
        />
      )}
    </>
  );
});
