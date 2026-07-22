"use client";

import { memo, useMemo } from "react";

import {
  jsonLdToGraph,
  layoutOntologyGraph,
  type OntologyGraphNode,
} from "@/lib/ontology-graph";
import { cn } from "@/lib/utils";

interface OntologyReasonGraphProps {
  jsonLd: string | null | undefined;
  className?: string;
  width?: number;
  height?: number;
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
    default:
      return "#475569";
  }
}

export const OntologyReasonGraph = memo(function OntologyReasonGraph({
  jsonLd,
  className,
  width = 360,
  height = 280,
}: OntologyReasonGraphProps) {
  const laidOut = useMemo(() => {
    const model = jsonLdToGraph(jsonLd);
    return layoutOntologyGraph(model, width, height);
  }, [jsonLd, width, height]);

  if (laidOut.nodes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No graphable JSON-LD in this reasoner response.
      </p>
    );
  }

  const byId = new Map(laidOut.nodes.map((node) => [node.id, node]));

  return (
    <div
      className={cn(
        "overflow-auto rounded-md border bg-muted/30",
        className,
      )}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Reasoner result ontology graph"
      >
        <defs>
          <marker
            id="ontology-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="6"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" />
          </marker>
        </defs>
        {laidOut.edges.map((edge) => {
          const source = byId.get(edge.source);
          const target = byId.get(edge.target);
          if (!source || !target) {
            return null;
          }
          const mx = (source.x + target.x) / 2;
          const my = (source.y + target.y) / 2;
          return (
            <g key={edge.id}>
              <line
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                stroke="#94a3b8"
                strokeWidth={1.25}
                markerEnd="url(#ontology-arrow)"
              />
              <text
                x={mx}
                y={my - 4}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 9 }}
              >
                {edge.label}
              </text>
            </g>
          );
        })}
        {laidOut.nodes.map((node) => {
          const label =
            node.label.length > 18
              ? `${node.label.slice(0, 16)}…`
              : node.label;
          const w = Math.max(56, Math.min(110, label.length * 7 + 16));
          const h = 28;
          return (
            <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
              <title>{`${node.label}\n${node.id}`}</title>
              <rect
                x={-w / 2}
                y={-h / 2}
                width={w}
                height={h}
                rx={8}
                fill={nodeFill(node.kind, node.focus)}
                opacity={0.92}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fill="#f8fafc"
                style={{ fontSize: 10, fontWeight: 600 }}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-2 border-t px-2 py-1.5 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-indigo-700" />{" "}
          class
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-sm bg-teal-700" />{" "}
          individual
        </span>
        <span className="inline-flex items-center gap-1">
          <span
            className="inline-block h-2 w-2 rounded-sm"
            style={{ background: "hsl(var(--primary))" }}
          />{" "}
          focus
        </span>
      </div>
    </div>
  );
});
