import type { OntologyGraphEdge, OntologyGraphNode } from "@/lib/ontology-graph";

export const ONTOLOGY_KIND_COLORS: Record<
  OntologyGraphNode["kind"],
  string
> = {
  class: "#4338ca",
  individual: "#0f766e",
  literal: "#b45309",
  result: "#64748b",
  document: "#1e3a5f",
  chunk: "#475569",
  other: "#57534e",
};

export function ontologyNodeColor(node: OntologyGraphNode): string {
  if (node.focus || node.shared) {
    return "#4f46e5";
  }
  return ONTOLOGY_KIND_COLORS[node.kind] || ONTOLOGY_KIND_COLORS.other;
}

export function ontologyElements(
  nodes: OntologyGraphNode[],
  edges: OntologyGraphEdge[],
) {
  return [
    ...nodes.map((node) => ({
      group: "nodes" as const,
      data: {
        id: node.id,
        label: node.label,
        kind: node.kind,
        weight: node.weight ?? 0,
        shared: node.shared ? 1 : 0,
        focus: node.focus ? 1 : 0,
        layer: node.layer ?? -1,
        color: ontologyNodeColor(node),
      },
    })),
    ...edges.map((edge) => ({
      group: "edges" as const,
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label || "",
        weight: edge.weight ?? 1,
      },
    })),
  ];
}

export const ONTOLOGY_CY_STYLE = [
  {
    selector: "node",
    style: {
      label: "data(label)",
      "background-color": "data(color)",
      color: "#f8fafc",
      "font-size": 12,
      "font-weight": 600,
      "text-wrap": "wrap",
      "text-max-width": "110px",
      "text-valign": "center",
      "text-halign": "center",
      "text-outline-width": 2,
      "text-outline-color": "data(color)",
      shape: "round-rectangle",
      width: "mapData(weight, 0, 12, 72, 128)",
      height: "mapData(weight, 0, 12, 36, 52)",
      padding: "8px",
      "border-width": 2,
      "border-color": "#e2e8f0",
      "overlay-padding": 4,
    },
  },
  {
    selector: "node[shared = 1], node[focus = 1]",
    style: {
      "border-width": 3,
      "border-color": "#c7d2fe",
    },
  },
  {
    selector: "node:selected",
    style: {
      "border-width": 4,
      "border-color": "#fbbf24",
      "overlay-opacity": 0.08,
    },
  },
  {
    selector: "node.faded",
    style: {
      opacity: 0.18,
    },
  },
  {
    selector: "node.match",
    style: {
      "border-width": 3,
      "border-color": "#38bdf8",
    },
  },
  {
    selector: "edge",
    style: {
      width: "mapData(weight, 1, 8, 1.5, 4.5)",
      "line-color": "#64748b",
      "target-arrow-color": "#64748b",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "arrow-scale": 1.1,
      label: "data(label)",
      "font-size": 10,
      color: "#cbd5e1",
      "text-rotation": "autorotate",
      "text-background-color": "#0f172a",
      "text-background-opacity": 0.82,
      "text-background-padding": "2px",
      "text-background-shape": "roundrectangle",
    },
  },
  {
    selector: "edge:selected, edge.highlighted",
    style: {
      "line-color": "#818cf8",
      "target-arrow-color": "#818cf8",
      width: 3,
      color: "#e0e7ff",
    },
  },
  {
    selector: "edge.faded",
    style: {
      opacity: 0.08,
      label: "",
    },
  },
];
