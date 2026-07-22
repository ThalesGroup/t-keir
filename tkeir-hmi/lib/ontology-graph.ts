/** Parse reasoner / fused ontology JSON-LD into a simple node–edge graph. */

export interface OntologyGraphNode {
  id: string;
  label: string;
  kind: "class" | "individual" | "literal" | "result" | "other";
  focus?: boolean;
}

export interface OntologyGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface OntologyGraphModel {
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
}

function localName(iri: string): string {
  const hash = iri.lastIndexOf("#");
  if (hash >= 0 && hash < iri.length - 1) {
    return iri.slice(hash + 1);
  }
  const slash = iri.lastIndexOf("/");
  if (slash >= 0 && slash < iri.length - 1) {
    return iri.slice(slash + 1);
  }
  return iri;
}

function asArray<T>(value: T | T[] | undefined | null): T[] {
  if (value == null) {
    return [];
  }
  return Array.isArray(value) ? value : [value];
}

function nodeKind(types: string[]): OntologyGraphNode["kind"] {
  const joined = types.join(" ").toLowerCase();
  if (joined.includes("queryresult") || joined.includes("resultset")) {
    return "result";
  }
  if (joined.includes("class")) {
    return "class";
  }
  if (joined.includes("namedindividual") || joined.includes("individual")) {
    return "individual";
  }
  return "other";
}

function predicateLabel(predicate: string): string {
  const name = localName(predicate);
  if (name === "subClassOf") {
    return "subClassOf";
  }
  if (name === "type") {
    return "type";
  }
  if (name === "hit" || name === "focus") {
    return name;
  }
  return name.length > 24 ? `${name.slice(0, 22)}…` : name;
}

type JsonLdNode = Record<string, unknown>;

/**
 * Build a display graph from a JSON-LD string (array or object).
 * Skips noisy result-set metadata predicates when richer edges exist.
 */
export function jsonLdToGraph(jsonLd: string | null | undefined): OntologyGraphModel {
  if (!jsonLd?.trim() || jsonLd.trim() === "[]") {
    return { nodes: [], edges: [] };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonLd);
  } catch {
    return { nodes: [], edges: [] };
  }

  const docs = asArray(parsed as JsonLdNode | JsonLdNode[]).filter(
    (item): item is JsonLdNode =>
      Boolean(item) && typeof item === "object" && !Array.isArray(item),
  );

  const nodes = new Map<string, OntologyGraphNode>();
  const edges: OntologyGraphEdge[] = [];
  let edgeSeq = 0;

  const ensureNode = (
    id: string,
    opts?: Partial<OntologyGraphNode>,
  ): OntologyGraphNode => {
    const existing = nodes.get(id);
    if (existing) {
      if (opts?.label && opts.label !== localName(id)) {
        existing.label = opts.label;
      }
      if (opts?.kind && existing.kind === "other") {
        existing.kind = opts.kind;
      }
      if (opts?.focus) {
        existing.focus = true;
      }
      return existing;
    }
    const created: OntologyGraphNode = {
      id,
      label: opts?.label || localName(id),
      kind: opts?.kind || "other",
      focus: opts?.focus,
    };
    nodes.set(id, created);
    return created;
  };

  for (const doc of docs) {
    const id = typeof doc["@id"] === "string" ? doc["@id"] : "";
    if (!id) {
      continue;
    }
    const types = asArray(doc["@type"]).map(String);
    const labels = asArray(
      doc["http://www.w3.org/2000/01/rdf-schema#label"] as
        | { "@value"?: string }
        | { "@value"?: string }[]
        | string
        | string[]
        | undefined,
    )
      .map((entry) => {
        if (typeof entry === "string") {
          return entry;
        }
        if (entry && typeof entry === "object" && "@value" in entry) {
          return String(entry["@value"] ?? "");
        }
        return "";
      })
      .filter(Boolean);
    ensureNode(id, {
      label: labels[0] || localName(id),
      kind: nodeKind(types),
    });
  }

  const skipPredicates = new Set([
    "http://www.w3.org/2000/01/rdf-schema#label",
    "http://tkeir.local/reasoner/backend",
    "http://tkeir.local/reasoner/engine",
    "http://tkeir.local/reasoner/operation",
    "http://tkeir.local/reasoner/hitCount",
    "http://tkeir.local/reasoner/consistent",
  ]);

  for (const doc of docs) {
    const source = typeof doc["@id"] === "string" ? doc["@id"] : "";
    if (!source) {
      continue;
    }
    for (const [predicate, raw] of Object.entries(doc)) {
      if (predicate.startsWith("@") || skipPredicates.has(predicate)) {
        continue;
      }
      for (const value of asArray(raw)) {
        let target = "";
        let literalLabel = "";
        if (typeof value === "string") {
          if (value.startsWith("http")) {
            target = value;
          } else {
            literalLabel = value;
          }
        } else if (value && typeof value === "object") {
          const obj = value as Record<string, unknown>;
          if (typeof obj["@id"] === "string") {
            target = obj["@id"];
          } else if (obj["@value"] != null) {
            literalLabel = String(obj["@value"]);
          }
        }
        if (literalLabel) {
          target = `literal:${source}:${predicate}:${literalLabel}`;
          ensureNode(target, {
            label: literalLabel.slice(0, 40),
            kind: "literal",
          });
        }
        if (!target) {
          continue;
        }
        ensureNode(source);
        ensureNode(target);
        if (predicate.endsWith("focus") || predicate.endsWith("/focus")) {
          const focusNode = nodes.get(target);
          if (focusNode) {
            focusNode.focus = true;
          }
        }
        // Prefer structural edges over result-set "hit" spokes when both exist.
        if (predicate.endsWith("/hit") || predicate.endsWith("#hit")) {
          continue;
        }
        edges.push({
          id: `e${edgeSeq++}`,
          source,
          target,
          label: predicateLabel(predicate),
        });
      }
    }
  }

  // If we skipped all hits and have almost no edges, re-add hit edges.
  if (edges.length === 0) {
    for (const doc of docs) {
      const source = typeof doc["@id"] === "string" ? doc["@id"] : "";
      if (!source) {
        continue;
      }
      const hits = asArray(
        doc["http://tkeir.local/reasoner/hit"] as
          | { "@id"?: string }
          | { "@id"?: string }[]
          | undefined,
      );
      for (const hit of hits) {
        const target =
          typeof hit === "object" && hit && typeof hit["@id"] === "string"
            ? hit["@id"]
            : "";
        if (!target) {
          continue;
        }
        ensureNode(source, { kind: "result" });
        ensureNode(target);
        edges.push({
          id: `e${edgeSeq++}`,
          source,
          target,
          label: "hit",
        });
      }
    }
  }

  return {
    nodes: Array.from(nodes.values()),
    edges,
  };
}

export interface LaidOutNode extends OntologyGraphNode {
  x: number;
  y: number;
}

/** Radial layout: focus (or first) node in the center, others on a ring. */
export function layoutOntologyGraph(
  model: OntologyGraphModel,
  width: number,
  height: number,
): { nodes: LaidOutNode[]; edges: OntologyGraphEdge[] } {
  if (model.nodes.length === 0) {
    return { nodes: [], edges: [] };
  }
  const cx = width / 2;
  const cy = height / 2;
  const focus =
    model.nodes.find((node) => node.focus) ||
    model.nodes.find((node) => node.kind === "class") ||
    model.nodes[0];
  const others = model.nodes.filter((node) => node.id !== focus.id);
  const radius = Math.min(width, height) * 0.36;
  const laid: LaidOutNode[] = [
    { ...focus, x: cx, y: cy },
    ...others.map((node, index) => {
      const angle =
        (Math.PI * 2 * index) / Math.max(others.length, 1) - Math.PI / 2;
      return {
        ...node,
        x: cx + radius * Math.cos(angle),
        y: cy + radius * Math.sin(angle),
      };
    }),
  ];
  return { nodes: laid, edges: model.edges };
}
