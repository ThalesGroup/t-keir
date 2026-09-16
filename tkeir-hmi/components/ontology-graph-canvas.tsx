"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type cytoscapeFactory from "cytoscape";
import type { Core, EventObject, LayoutOptions, NodeSingular } from "cytoscape";
import {
  CircleDot,
  Focus,
  LocateFixed,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  Waypoints,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ONTOLOGY_CY_STYLE,
  ontologyElements,
} from "@/lib/ontology-cy-style";
import type {
  OntologyGraphEdge,
  OntologyGraphModel,
  OntologyGraphNode,
} from "@/lib/ontology-graph";
import { cn } from "@/lib/utils";

export type OntologyLayoutKind = "force" | "radial" | "tree";

type CytoscapeFactory = typeof cytoscapeFactory;

let cytoscapeReady: Promise<CytoscapeFactory> | null = null;

function loadCytoscape() {
  if (!cytoscapeReady) {
    cytoscapeReady = (async () => {
      const cytoscapeMod = await import("cytoscape");
      const cytoscape = (
        "default" in cytoscapeMod && cytoscapeMod.default
          ? cytoscapeMod.default
          : cytoscapeMod
      ) as CytoscapeFactory;
      const fcoseMod = await import("cytoscape-fcose");
      const fcose = (
        "default" in fcoseMod ? fcoseMod.default : fcoseMod
      ) as (api: CytoscapeFactory) => void;
      cytoscape.use(fcose);
      return cytoscape;
    })();
  }
  return cytoscapeReady;
}

function runLayout(cy: Core, kind: OntologyLayoutKind) {
  const common = {
    animate: true,
    animationDuration: 380,
    fit: true,
    padding: 28,
  };
  if (kind === "radial") {
    cy.layout({
      name: "concentric",
      ...common,
      minNodeSpacing: 28,
      concentric: (node: NodeSingular) =>
        Number(node.data("weight") || 0) + (node.degree(false) || 0),
      levelWidth: () => 2,
    }).run();
    return;
  }
  if (kind === "tree") {
    const roots = cy.nodes().filter((node) => node.data("kind") === "document");
    cy.layout({
      name: "breadthfirst",
      ...common,
      directed: true,
      spacingFactor: 1.25,
      roots: roots.length ? roots.map((node) => node.id()) : undefined,
    }).run();
    return;
  }
  try {
    cy.layout({
      name: "fcose",
      ...common,
      quality: "proof",
      randomize: false,
      nodeDimensionsIncludeLabels: true,
      idealEdgeLength: 92,
      nodeRepulsion: () => 6500,
      edgeElasticity: () => 0.45,
      gravity: 0.25,
      numIter: 2500,
    } as LayoutOptions).run();
  } catch {
    cy.layout({ name: "cose", ...common }).run();
  }
}

function neighborhoodIds(cy: Core, nodeId: string): Set<string> {
  const node = cy.getElementById(nodeId);
  const ids = new Set<string>([nodeId]);
  if (node.empty()) return ids;
  node.neighborhood().forEach((el) => {
    if (el.isNode()) ids.add(el.id());
  });
  return ids;
}

export function OntologyGraphCanvas({
  model,
  className,
  showInspector = true,
  defaultLayout = "force",
  minHeight = 256,
}: {
  model: OntologyGraphModel;
  className?: string;
  showInspector?: boolean;
  defaultLayout?: OntologyLayoutKind;
  minHeight?: number;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [layout, setLayout] = useState<OntologyLayoutKind>(defaultLayout);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isolated, setIsolated] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setLayout(defaultLayout);
  }, [defaultLayout]);

  const selectedNode = useMemo(
    () => model.nodes.find((node) => node.id === selectedId) ?? null,
    [model.nodes, selectedId],
  );
  const selectedEdges = useMemo(() => {
    if (!selectedId) return [] as OntologyGraphEdge[];
    return model.edges.filter(
      (edge) => edge.source === selectedId || edge.target === selectedId,
    );
  }, [model.edges, selectedId]);

  const applyEmphasis = useCallback(
    (cy: Core, nodeId: string | null, isolate: boolean) => {
      cy.batch(() => {
        cy.elements().removeClass("faded highlighted");
        cy.elements().style("display", "element");
        if (!nodeId) return;
        const keep = neighborhoodIds(cy, nodeId);
        cy.nodes().forEach((node) => {
          const visible = keep.has(node.id());
          if (isolate) {
            node.style("display", visible ? "element" : "none");
          } else if (!visible) {
            node.addClass("faded");
          }
        });
        cy.edges().forEach((edge) => {
          const keepEdge =
            keep.has(edge.source().id()) && keep.has(edge.target().id());
          if (isolate) {
            edge.style("display", keepEdge ? "element" : "none");
            if (keepEdge) edge.addClass("highlighted");
          } else if (keepEdge) {
            edge.addClass("highlighted");
          } else {
            edge.addClass("faded");
          }
        });
      });
      if (isolate && nodeId) {
        const focus = cy.getElementById(nodeId);
        if (!focus.empty()) {
          cy.fit(focus.closedNeighborhood(), 48);
        }
      }
    },
    [],
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;
    let cy: Core | null = null;

    void loadCytoscape().then((cytoscape) => {
      if (cancelled || !hostRef.current) return;
      const instance = cytoscape({
        container: hostRef.current,
        elements: ontologyElements(model.nodes, model.edges),
        style: ONTOLOGY_CY_STYLE as never,
        minZoom: 0.2,
        maxZoom: 3.5,
        wheelSensitivity: 0.22,
        boxSelectionEnabled: false,
        autoungrabify: false,
        pixelRatio: "auto",
      });
      cy = instance;
      cyRef.current = instance;
      runLayout(instance, layout);
      requestAnimationFrame(() => {
        if (cancelled) return;
        instance.resize();
        instance.fit(undefined, 28);
      });
      instance.on("tap", "node", (event: EventObject) => {
        const id = event.target.id();
        setSelectedId((prev) => (prev === id ? null : id));
      });
      instance.on("tap", (event: EventObject) => {
        if (event.target === instance) {
          setSelectedId(null);
          setIsolated(false);
        }
      });
      instance.on("dbltap", "node", (event: EventObject) => {
        setSelectedId(event.target.id());
        setIsolated(true);
      });
      setReady(true);
    });

    return () => {
      cancelled = true;
      cy?.destroy();
      cyRef.current = null;
      setReady(false);
    };
    // Recreate when the graph membership changes, not on layout/filter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    applyEmphasis(cy, selectedId, isolated);
    if (selectedId) {
      cy.getElementById(selectedId).select();
    } else {
      cy.nodes().unselect();
    }
  }, [applyEmphasis, isolated, ready, selectedId]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    const q = filter.trim().toLowerCase();
    cy.batch(() => {
      cy.nodes().removeClass("match");
      if (!q) return;
      cy.nodes().forEach((node) => {
        const label = String(node.data("label") || "").toLowerCase();
        const id = node.id().toLowerCase();
        const kind = String(node.data("kind") || "").toLowerCase();
        if (label.includes(q) || id.includes(q) || kind.includes(q)) {
          node.addClass("match");
        }
      });
    });
  }, [filter, ready]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !ready) return;
    runLayout(cy, layout);
  }, [layout, ready]);

  useEffect(() => {
    const host = hostRef.current;
    const cy = cyRef.current;
    if (!host || !cy || !ready) return;
    const observer = new ResizeObserver(() => {
      cy.resize();
    });
    observer.observe(host);
    return () => observer.disconnect();
  }, [ready]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.zoom({
      level: Math.min(3.5, Math.max(0.2, cy.zoom() * factor)),
      renderedPosition: {
        x: cy.width() / 2,
        y: cy.height() / 2,
      },
    });
  };

  const fitView = () => {
    cyRef.current?.fit(undefined, 32);
  };

  const resetView = () => {
    setSelectedId(null);
    setIsolated(false);
    setFilter("");
    runLayout(cyRef.current as Core, layout);
  };

  const focusNode = (node: OntologyGraphNode) => {
    const cy = cyRef.current;
    setSelectedId(node.id);
    if (!cy) return;
    const el = cy.getElementById(node.id);
    if (el.empty()) return;
    cy.animate({
      center: { eles: el },
      zoom: Math.max(cy.zoom(), 1.15),
      duration: 220,
    });
  };

  const listNodes = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const rows = q
      ? model.nodes.filter(
          (node) =>
            node.label.toLowerCase().includes(q) ||
            node.id.toLowerCase().includes(q) ||
            node.kind.toLowerCase().includes(q),
        )
      : model.nodes;
    return [...rows].sort(
      (a, b) =>
        (b.weight ?? 0) - (a.weight ?? 0) || a.label.localeCompare(b.label),
    );
  }, [filter, model.nodes]);

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="flex flex-wrap items-center gap-2 border-b px-2 py-2">
        <div className="relative min-w-[10rem] flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Find a concept…"
            className="h-9 pl-8"
            aria-label="Filter ontology nodes"
          />
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {(
            [
              ["force", "Force", Waypoints],
              ["radial", "Radial", CircleDot],
              ["tree", "Tree", Sparkles],
            ] as const
          ).map(([id, label, Icon]) => (
            <Button
              key={id}
              type="button"
              size="sm"
              variant={layout === id ? "secondary" : "ghost"}
              className="h-9 gap-1 px-2"
              onClick={() => setLayout(id)}
              title={`${label} layout`}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </Button>
          ))}
          <Button
            type="button"
            size="sm"
            variant={isolated ? "secondary" : "ghost"}
            className="h-9 gap-1 px-2"
            disabled={!selectedId}
            onClick={() => setIsolated((value) => !value)}
            title="Show only the selected concept and its neighbors"
          >
            <Focus className="h-4 w-4" />
            <span className="hidden lg:inline">1-hop</span>
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={() => zoomBy(0.85)}
            title="Zoom out"
          >
            <Minus className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={() => zoomBy(1.15)}
            title="Zoom in"
          >
            <Plus className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={fitView}
            title="Fit graph"
          >
            <LocateFixed className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9"
            onClick={resetView}
            title="Reset layout"
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div
        className={cn(
          "relative grid min-h-0 flex-1",
          showInspector
            ? "lg:grid-cols-[minmax(0,1fr)_17rem]"
            : "grid-cols-1",
        )}
        style={{ minHeight }}
      >
        <div className="relative h-full min-h-0 min-w-0">
          {!ready ? (
            <div className="absolute inset-0 z-10 flex items-center justify-center text-sm text-muted-foreground">
              Loading graph…
            </div>
          ) : null}
          <div
            ref={hostRef}
            className="absolute inset-0 h-full w-full bg-slate-950/40"
            style={{ minHeight }}
            role="img"
            aria-label="Interactive ontology graph"
          />
        </div>
        {showInspector ? (
          <aside className="flex min-h-0 flex-col border-t bg-card/70 lg:border-l lg:border-t-0">
            <div className="border-b px-3 py-2 text-sm text-muted-foreground">
              {model.nodes.length} concepts · {model.edges.length} links
              {filter ? ` · ${listNodes.length} matches` : ""}
            </div>
            <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
              {listNodes.map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    className={cn(
                      "flex w-full flex-col rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted",
                      selectedId === node.id && "bg-primary/10 text-primary",
                    )}
                    onClick={() => focusNode(node)}
                  >
                    <span className="truncate font-medium">{node.label}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {node.kind}
                      {node.shared ? " · shared" : ""}
                    </span>
                  </button>
                </li>
              ))}
              {listNodes.length === 0 && (
                <li className="px-2 py-4 text-sm text-muted-foreground">
                  No concepts match that filter.
                </li>
              )}
            </ul>
            {selectedNode ? (
              <div className="space-y-2 border-t p-3 text-sm">
                <p className="font-semibold leading-snug">
                  {selectedNode.label}
                </p>
                <div className="flex flex-wrap gap-1">
                  <Badge variant="outline">{selectedNode.kind}</Badge>
                  {selectedNode.shared ? (
                    <Badge variant="secondary">shared</Badge>
                  ) : null}
                  {selectedNode.weight != null && selectedNode.weight > 0 ? (
                    <Badge variant="outline">
                      weight {selectedNode.weight.toFixed(1)}
                    </Badge>
                  ) : null}
                </div>
                <p className="text-muted-foreground">
                  {selectedEdges.length} linked{" "}
                  {selectedEdges.length === 1 ? "relation" : "relations"}
                  {isolated ? " · 1-hop only" : " · click 1-hop to isolate"}
                </p>
                <ul className="max-h-28 space-y-1 overflow-y-auto text-xs">
                  {selectedEdges.slice(0, 12).map((edge) => {
                    const otherId =
                      edge.source === selectedNode.id
                        ? edge.target
                        : edge.source;
                    const other =
                      model.nodes.find((node) => node.id === otherId)?.label ||
                      otherId;
                    const inbound = edge.target === selectedNode.id;
                    return (
                      <li key={edge.id}>
                        <button
                          type="button"
                          className="w-full truncate text-left hover:text-primary"
                          onClick={() => {
                            const node = model.nodes.find(
                              (item) => item.id === otherId,
                            );
                            if (node) focusNode(node);
                          }}
                        >
                          {inbound ? "←" : "→"} {edge.label || "related"}{" "}
                          {other}
                        </button>
                      </li>
                    );
                  })}
                </ul>
                <p className="break-all font-mono text-[11px] text-muted-foreground">
                  {selectedNode.id}
                </p>
              </div>
            ) : (
              <p className="border-t px-3 py-2 text-xs text-muted-foreground">
                Click a node, or a name in the list. Double-click isolates
                neighbors. Drag nodes to tidy the layout. Scroll to zoom.
              </p>
            )}
          </aside>
        ) : null}
      </div>
    </div>
  );
}
