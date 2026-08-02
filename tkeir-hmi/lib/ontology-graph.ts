/** Parse reasoner / fused ontology JSON-LD into a simple node–edge graph. */

export interface OntologyGraphNode {
  id: string;
  label: string;
  kind: "class" | "individual" | "literal" | "result" | "other" | "document" | "chunk";
  focus?: boolean;
  /** Text-importance / fuse weight from the API (higher = more central). */
  weight?: number;
  /** Document→chunk→concept band for layered layout (0=doc, 1=chunk, 2=concept). */
  layer?: 0 | 1 | 2;
  /** Concept evidenced in ≥2 chunks (set intersection / shared ontology). */
  shared?: boolean;
}

export interface OntologyGraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  /** Fuse-summed relation weight (higher = more evidenced across chunks). */
  weight?: number;
}

export interface OntologyGraphModel {
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
}

export interface OntologyWeightMaps {
  /** Label (case-insensitive) → node weight */
  nodeWeights?: Record<string, number>;
  /** `${source}|${predicate}|${target}` (case-insensitive) → link weight */
  linkWeights?: Record<string, number>;
}

/**
 * True for Document / DocumentChunk / path-like labels that must not appear
 * as peer SPO concept nodes (they drown the analyst graph).
 */
export function isScaffoldingConceptLabel(label: string): boolean {
  const text = (label || "").trim();
  if (text.length < 2) return true;
  if (/#chunk-\d+/i.test(text)) return true;
  if (/\.(md|pdf|txt|html|json)($|[?#\s])/i.test(text)) return true;
  if (/\/Chunk\//i.test(text) || /\/Keyword\//i.test(text)) return true;
  // Long path-like source_ref labels.
  if (text.includes("/") && text.length > 48) return true;
  // Ingest doc_key stems (c2_202607_0398) — keep for document layer only.
  if (/^[a-z0-9]+_\d{5,}_\d+$/i.test(text)) return true;
  if (/^chunk-\d+/i.test(text)) return true;
  return false;
}

export function isScaffoldingEntityType(type: string | undefined | null): boolean {
  const t = (type || "").toLowerCase();
  if (!t) return false;
  return (
    t.includes("documentchunk") ||
    t === "document" ||
    t.endsWith(":document") ||
    t.includes("keyword") ||
    t.includes("tag") ||
    t === "metric"
  );
}

/** Shorten a document id/path for the containment layer. */
export function shortDocumentLabel(docId: string): string {
  const raw = (docId || "").trim();
  if (!raw) return "document";
  const base = raw.split("/").pop() || raw;
  const noExt = base.replace(/\.(md|pdf|txt|html|json)$/i, "");
  return noExt.length > 36 ? `${noExt.slice(0, 34)}…` : noExt;
}

/** Shorten a chunk id to chunk-N (or a compact token). */
export function shortChunkLabel(chunkId: string): string {
  const raw = (chunkId || "").trim();
  if (!raw) return "chunk";
  const m = raw.match(/#?(chunk-\d+)/i);
  if (m) return m[1].toLowerCase();
  const tail = raw.split("/").pop() || raw;
  return tail.length > 28 ? `${tail.slice(0, 26)}…` : tail;
}

/** Build node/link weight maps from a fused ontology payload (for graph prune). */
export function weightMapsFromOntology(ontology: {
  entities?: Array<{
    label: string;
    weight?: number;
    chunk_ids?: string[];
  }>;
  keywords?: Array<{
    label: string;
    weight?: number;
    chunk_ids?: string[];
  }>;
  relations?: Array<{
    source: string;
    target: string;
    predicate: string;
    weight?: number;
  }>;
} | null | undefined): OntologyWeightMaps | null {
  if (!ontology) return null;
  const nodeWeights: Record<string, number> = {};
  for (const entity of ontology.entities ?? []) {
    const key = entity.label.trim().toLowerCase();
    if (!key) continue;
    if (isScaffoldingConceptLabel(entity.label)) continue;
    const weight =
      entity.weight ?? Math.max(1, entity.chunk_ids?.length ?? 0) * 10;
    // Shared (multi-chunk) concepts rank higher for intersection views.
    const sharedBoost = (entity.chunk_ids?.length ?? 0) >= 2 ? 1.5 : 1;
    nodeWeights[key] = Math.max(
      nodeWeights[key] ?? 0,
      weight * sharedBoost,
    );
  }
  // Keywords stay in the navigator — they flood the SPO canvas if weighted here.
  const linkWeights: Record<string, number> = {};
  for (const relation of ontology.relations ?? []) {
    const source = (relation.source || "").trim().toLowerCase();
    const target = (relation.target || "").trim().toLowerCase();
    const predicateRaw = (relation.predicate || "").trim();
    if (!source || !target || !predicateRaw) continue;
    if (isStructuralDisplayPredicate(predicateRaw)) continue;
    if (
      isScaffoldingConceptLabel(relation.source) ||
      isScaffoldingConceptLabel(relation.target)
    ) {
      continue;
    }
    // Match edge labels after humanizePredicateLabel in jsonLdToGraph / inject.
    const predicate = humanizePredicateLabel(predicateRaw).toLowerCase();
    if (!predicate) continue;
    const key = `${source}|${predicate}|${target}`;
    // Boost verbal kg edges so prune-by-weight keeps them over residual links.
    const weight = Math.max(1, (relation.weight ?? 1) * 3);
    linkWeights[key] = Math.max(linkWeights[key] ?? 0, weight);
  }
  if (
    Object.keys(nodeWeights).length === 0 &&
    Object.keys(linkWeights).length === 0
  ) {
    return null;
  }
  return { nodeWeights, linkWeights };
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
  // Keep the full local name so fuse-exported relation weights can match.
  // UI layers truncate for display.
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
  return name;
}

/** RDF / TKEIR scaffolding — hide on the analyst graph so kg verbs stand out. */
const STRUCTURAL_EDGE_LOCAL_NAMES = new Set([
  "haskeyword",
  "hasmention",
  "haschunk",
  "hasstatement",
  "hastag",
  "istagof",
  "hasnumericvalue",
  "hascontent",
  "importancescore",
  "linkweight",
  "mentionedin",
  "inchunk",
  "hassubontology",
  "chunksupport",
  "sharedconceptcount",
  "intersectionweight",
  "ontologypath",
  "ontologypathids",
  "ontologypathlabels",
  "ontologypathtext",
  "ontologypathcompact",
  "mapstoconcept",
  "maps_to_concept",
  "provenance",
  "preferred_label",
  "matched_in_text",
  "role",
  "type",
  "label",
]);

function isStructuralDisplayPredicate(predicate: string): boolean {
  const local = localName(predicate).toLowerCase().replace(/[_-]/g, "");
  if (STRUCTURAL_EDGE_LOCAL_NAMES.has(local)) {
    return true;
  }
  // Compact forms: tkeir:hasKeyword
  const compact = predicate.toLowerCase();
  return (
    compact.includes("haskeyword") ||
    compact.includes("hasmention") ||
    compact.includes("haschunk") ||
    compact.includes("hasstatement") ||
    compact.includes("hastag")
  );
}

/** Humanize camelCase / URI local names for edge labels (held, identifiedAs). */
export function humanizePredicateLabel(predicate: string): string {
  const raw = predicateLabel(predicate).trim();
  if (!raw) return raw;
  if (/\s/.test(raw)) return raw;
  return raw
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .toLowerCase();
}

type JsonLdNode = Record<string, unknown>;

function expandJsonLdNodes(parsed: unknown): JsonLdNode[] {
  const out: JsonLdNode[] = [];
  const pushNode = (item: unknown) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      return;
    }
    const node = item as JsonLdNode;
    // Compact JSON-LD document wrapper — expand @graph, ignore bare context.
    if (Array.isArray(node["@graph"])) {
      for (const child of node["@graph"] as unknown[]) {
        pushNode(child);
      }
      return;
    }
    if (typeof node["@id"] === "string" && node["@id"]) {
      out.push(node);
    }
  };

  if (Array.isArray(parsed)) {
    for (const item of parsed) {
      pushNode(item);
    }
    return out;
  }
  pushNode(parsed);
  return out;
}

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

  const docs = expandJsonLdNodes(parsed);

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
      if (
        opts?.weight != null &&
        (existing.weight == null || opts.weight > existing.weight)
      ) {
        existing.weight = opts.weight;
      }
      return existing;
    }
    const created: OntologyGraphNode = {
      id,
      label: opts?.label || localName(id),
      kind: opts?.kind || "other",
      focus: opts?.focus,
      weight: opts?.weight,
    };
    nodes.set(id, created);
    return created;
  };

  const labelFromValue = (entry: unknown): string => {
    if (typeof entry === "string") {
      return entry;
    }
    if (entry && typeof entry === "object" && "@value" in entry) {
      return String((entry as { "@value"?: string })["@value"] ?? "");
    }
    return "";
  };

  for (const doc of docs) {
    const id = typeof doc["@id"] === "string" ? doc["@id"] : "";
    if (!id) {
      continue;
    }
    const types = asArray(doc["@type"]).map(String);
    const joinedTypes = types.join(" ").toLowerCase();
    // Never materialize Document / Chunk / Keyword as concept peers.
    if (
      joinedTypes.includes("documentchunk") ||
      /(^|[^\w])document([^\w]|$)/.test(joinedTypes) ||
      joinedTypes.includes("keyword") ||
      joinedTypes.includes("/tag") ||
      joinedTypes.endsWith("tag")
    ) {
      // Still allow Keyword/Tag only if we later need labels — skip entirely.
      continue;
    }
    const labelCandidates = [
      ...asArray(
        doc["http://www.w3.org/2000/01/rdf-schema#label"] as
          | { "@value"?: string }
          | { "@value"?: string }[]
          | string
          | string[]
          | undefined,
      ),
      ...asArray(doc["rdfs:label"] as string | string[] | undefined),
      ...asArray(doc["name"] as string | string[] | undefined),
      ...asArray(doc["schema:name"] as string | string[] | undefined),
    ]
      .map(labelFromValue)
      .filter(Boolean);
    // Node weights come from fused API maps (entities/keywords), not RDF
    // technical predicates such as importanceScore.
    ensureNode(id, {
      label: labelCandidates[0] || localName(id),
      kind: nodeKind(types),
    });
  }

  const skipPredicates = new Set([
    "http://www.w3.org/2000/01/rdf-schema#label",
    "rdfs:label",
    "name",
    "schema:name",
    "schema:alternateName",
    "alternateName",
    "identifier",
    "schema:identifier",
    "schema:provenance",
    "http://tkeir.local/ontology/importanceScore",
    "importanceScore",
    "http://tkeir.local/ontology/linkWeight",
    "linkWeight",
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
      // Prefer kg/SVO verbal edges over Document scaffolding.
      if (isStructuralDisplayPredicate(predicate)) {
        continue;
      }
      for (const value of asArray(raw)) {
        let target = "";
        let literalLabel = "";
        if (typeof value === "string") {
          if (
            value.startsWith("http") ||
            value.startsWith("urn:") ||
            value.includes("://")
          ) {
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
          // Skip long synonym dumps — they inflate degree without structure.
          if (literalLabel.length > 80) {
            continue;
          }
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
          label: humanizePredicateLabel(predicate),
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

  return dropScaffoldingNodes({
    nodes: Array.from(nodes.values()),
    edges,
  });
}

export type OntologyRelationEdge = {
  source: string;
  predicate: string;
  target: string;
  weight?: number;
};

/**
 * Inject fused API relations (kg / SVO verbal predicates) into the display graph.
 *
 * JSON-LD often emphasizes scaffolding; search fuse exports precise verbs from
 * analyzed ``kg`` in ``relations``. Merge those so the graph shows e.g.
 * ``held`` / ``identified as`` instead of only structural links.
 */
export function injectOntologyRelations(
  model: OntologyGraphModel,
  relations?: OntologyRelationEdge[] | null,
): OntologyGraphModel {
  if (!relations?.length) {
    return model;
  }

  const nodes = [...model.nodes];
  const byLabel = new Map<string, OntologyGraphNode>();
  for (const node of nodes) {
    const key = node.label.trim().toLowerCase();
    if (key && !byLabel.has(key)) {
      byLabel.set(key, node);
    }
  }

  let edgeSeq = model.edges.length;
  const edges = [...model.edges];
  const seen = new Set(
    edges.map(
      (edge) =>
        `${edge.source}\0${(edge.label || "").toLowerCase()}\0${edge.target}`,
    ),
  );

  const ensureByLabel = (label: string): OntologyGraphNode | null => {
    const text = (label || "").trim();
    if (text.length < 2) return null;
    const key = text.toLowerCase();
    const existing = byLabel.get(key);
    if (existing) return existing;
    const id = `rel-node:${encodeURIComponent(key)}`;
    const created: OntologyGraphNode = {
      id,
      label: text.slice(0, 120),
      kind: "individual",
      weight: 20,
    };
    nodes.push(created);
    byLabel.set(key, created);
    return created;
  };

  for (const rel of relations) {
    const predRaw = (rel.predicate || "").trim();
    if (!predRaw || isStructuralDisplayPredicate(predRaw)) {
      continue;
    }
    const source = ensureByLabel(rel.source);
    const target = ensureByLabel(rel.target);
    if (!source || !target) continue;
    const label = humanizePredicateLabel(predRaw);
    const key = `${source.id}\0${label.toLowerCase()}\0${target.id}`;
    if (seen.has(key)) {
      const existing = edges.find(
        (edge) =>
          edge.source === source.id &&
          edge.target === target.id &&
          (edge.label || "").toLowerCase() === label.toLowerCase(),
      );
      if (existing && rel.weight != null) {
        existing.weight = Math.max(existing.weight ?? 0, rel.weight * 3);
      }
      continue;
    }
    seen.add(key);
    edges.push({
      id: `rel${edgeSeq++}`,
      source: source.id,
      target: target.id,
      label,
      weight: Math.max(3, (rel.weight ?? 1) * 3),
    });
  }

  return { nodes, edges };
}

export type OntologyGraphViewMode = "concepts" | "layered";

export type AnalystOntologyInput = {
  entities?: Array<{
    label: string;
    type?: string;
    weight?: number;
    chunk_ids?: string[];
  }>;
  keywords?: Array<{
    label: string;
    weight?: number;
    chunk_ids?: string[];
  }>;
  relations?: OntologyRelationEdge[] | null;
  json_ld?: string | null;
  document_ids?: string[] | null;
  chunks?: Array<{ chunk_id: string; parent_doc_id: string }> | null;
};

/**
 * Analyst display graph: SPO concepts first (S —P→ O), not Document/Chunk/Keyword flood.
 *
 * - ``concepts`` (default): verbal kg/RDF relations + shared entities only.
 * - ``layered``: Document → Chunk → concept ontology, with shared concepts
 *   (chunk-set intersection) highlighted as focus hubs.
 */
export function buildAnalystOntologyGraph(
  input: AnalystOntologyInput | null | undefined,
  options?: {
    mode?: OntologyGraphViewMode;
    includeKeywords?: boolean;
  },
): OntologyGraphModel {
  const mode = options?.mode ?? "concepts";
  const includeKeywords = Boolean(options?.includeKeywords);
  const entities = input?.entities ?? [];
  const relations = (input?.relations ?? []).filter(
    (rel) =>
      rel &&
      (rel.source || "").trim() &&
      (rel.predicate || "").trim() &&
      !isStructuralDisplayPredicate(rel.predicate) &&
      !isScaffoldingConceptLabel(rel.source) &&
      !(rel.target && isScaffoldingConceptLabel(rel.target)),
  );

  const nodes: OntologyGraphNode[] = [];
  const byLabel = new Map<string, OntologyGraphNode>();
  const edges: OntologyGraphEdge[] = [];
  let edgeSeq = 0;

  const ensureConcept = (
    label: string,
    opts?: Partial<OntologyGraphNode>,
  ): OntologyGraphNode | null => {
    const text = (label || "").trim();
    if (text.length < 2 || isScaffoldingConceptLabel(text)) return null;
    const key = text.toLowerCase();
    const existing = byLabel.get(key);
    if (existing) {
      if (opts?.weight != null) {
        existing.weight = Math.max(existing.weight ?? 0, opts.weight);
      }
      if (opts?.shared) existing.shared = true;
      if (opts?.focus) existing.focus = true;
      return existing;
    }
    const created: OntologyGraphNode = {
      id: `concept:${encodeURIComponent(key)}`,
      label: text.slice(0, 120),
      kind: "individual",
      layer: 2,
      weight: opts?.weight ?? 1,
      shared: opts?.shared,
      focus: opts?.focus || opts?.shared,
    };
    nodes.push(created);
    byLabel.set(key, created);
    return created;
  };

  const chunkIdsByLabel = new Map<string, Set<string>>();
  for (const entity of entities) {
    if (isScaffoldingEntityType(entity.type)) continue;
    if (isScaffoldingConceptLabel(entity.label)) continue;
    const key = entity.label.trim().toLowerCase();
    if (!key) continue;
    const set = chunkIdsByLabel.get(key) ?? new Set<string>();
    for (const cid of entity.chunk_ids ?? []) {
      if (cid) set.add(String(cid));
    }
    chunkIdsByLabel.set(key, set);
  }

  // Primary: explicit SPO from analyzed kg / fused relations.
  for (const rel of relations) {
    const pred = humanizePredicateLabel(rel.predicate);
    if (!pred) continue;
    const sourceChunks = chunkIdsByLabel.get(rel.source.trim().toLowerCase());
    const targetChunks = chunkIdsByLabel.get(
      (rel.target || "").trim().toLowerCase(),
    );
    const sharedSource = (sourceChunks?.size ?? 0) >= 2;
    const sharedTarget = (targetChunks?.size ?? 0) >= 2;
    const source = ensureConcept(rel.source, {
      weight: Math.max(3, (rel.weight ?? 1) * 2),
      shared: sharedSource,
      focus: sharedSource,
    });
    const target = ensureConcept(rel.target || "", {
      weight: Math.max(3, (rel.weight ?? 1) * 2),
      shared: sharedTarget,
      focus: sharedTarget,
    });
    if (!source || !target) continue;
    edges.push({
      id: `spo${edgeSeq++}`,
      source: source.id,
      target: target.id,
      label: pred,
      weight: Math.max(3, (rel.weight ?? 1) * 3),
    });
  }

  // Shared / high-weight entities fill gaps when kg is sparse.
  for (const entity of entities) {
    if (isScaffoldingEntityType(entity.type)) continue;
    if (isScaffoldingConceptLabel(entity.label)) continue;
    const chunks = chunkIdsByLabel.get(entity.label.trim().toLowerCase());
    const shared = (chunks?.size ?? 0) >= 2;
    const weight =
      entity.weight ?? Math.max(1, entity.chunk_ids?.length ?? 0) * 10;
    // Prefer shared intersection nodes; skip lonely isolates without SPO.
    const already = byLabel.has(entity.label.trim().toLowerCase());
    if (!already && !shared && weight < 8) continue;
    ensureConcept(entity.label, {
      weight: shared ? weight * 1.5 : weight,
      shared,
      focus: shared,
    });
  }

  if (includeKeywords) {
    for (const keyword of input?.keywords ?? []) {
      if (isScaffoldingConceptLabel(keyword.label)) continue;
      const shared = (keyword.chunk_ids?.length ?? 0) >= 2;
      ensureConcept(keyword.label, {
        weight: (keyword.weight ?? 1) * 0.5,
        shared,
      });
    }
  }

  // If relations were empty, reinforce from cleaned JSON-LD verbal edges.
  if (edges.length === 0 && input?.json_ld?.trim()) {
    const fromLd = dropScaffoldingNodes(
      injectOntologyRelations(jsonLdToGraph(input.json_ld), relations),
    );
    for (const node of fromLd.nodes) {
      ensureConcept(node.label, {
        weight: node.weight,
        kind: node.kind === "class" ? "class" : "individual",
      });
    }
    for (const edge of fromLd.edges) {
      const sourceNode = fromLd.nodes.find((n) => n.id === edge.source);
      const targetNode = fromLd.nodes.find((n) => n.id === edge.target);
      if (!sourceNode || !targetNode) continue;
      const source = ensureConcept(sourceNode.label);
      const target = ensureConcept(targetNode.label);
      if (!source || !target) continue;
      edges.push({
        id: `spo${edgeSeq++}`,
        source: source.id,
        target: target.id,
        label: edge.label,
        weight: edge.weight ?? 2,
      });
    }
  }

  // Drop concept isolates with no SPO links (unless shared intersection).
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  let conceptNodes = nodes.filter(
    (node) =>
      node.kind === "document" ||
      node.kind === "chunk" ||
      (degree.get(node.id) ?? 0) > 0 ||
      node.shared,
  );

  if (mode === "layered") {
    const docIds = new Set<string>();
    for (const id of input?.document_ids ?? []) {
      if (id?.trim()) docIds.add(id.trim());
    }
    for (const chunk of input?.chunks ?? []) {
      if (chunk.parent_doc_id?.trim()) docIds.add(chunk.parent_doc_id.trim());
    }

    const docNodes = new Map<string, OntologyGraphNode>();
    for (const docId of docIds) {
      const id = `doc:${encodeURIComponent(docId.toLowerCase())}`;
      const node: OntologyGraphNode = {
        id,
        label: shortDocumentLabel(docId),
        kind: "document",
        layer: 0,
        weight: 5,
      };
      docNodes.set(docId.toLowerCase(), node);
      conceptNodes = [...conceptNodes, node];
    }

    const chunkNodes = new Map<string, OntologyGraphNode>();
    for (const chunk of input?.chunks ?? []) {
      const cid = chunk.chunk_id?.trim();
      if (!cid) continue;
      const id = `chunk:${encodeURIComponent(cid.toLowerCase())}`;
      const node: OntologyGraphNode = {
        id,
        label: shortChunkLabel(cid),
        kind: "chunk",
        layer: 1,
        weight: 4,
      };
      chunkNodes.set(cid.toLowerCase(), node);
      conceptNodes = [...conceptNodes, node];
      const parent = chunk.parent_doc_id?.trim().toLowerCase();
      const doc = parent ? docNodes.get(parent) : undefined;
      if (doc) {
        edges.push({
          id: `contain${edgeSeq++}`,
          source: doc.id,
          target: node.id,
          label: "contains",
          weight: 1,
        });
      }
    }

    // Chunk → concept membership (hypergraph incidence).
    for (const entity of entities) {
      if (isScaffoldingEntityType(entity.type)) continue;
      if (isScaffoldingConceptLabel(entity.label)) continue;
      const concept = byLabel.get(entity.label.trim().toLowerCase());
      if (!concept) continue;
      for (const cid of entity.chunk_ids ?? []) {
        const chunk = chunkNodes.get(String(cid).toLowerCase());
        if (!chunk) continue;
        edges.push({
          id: `in${edgeSeq++}`,
          source: chunk.id,
          target: concept.id,
          label: "in",
          weight: concept.shared ? 2 : 1,
        });
      }
    }
  }

  // Recompute byLabel membership for returned nodes.
  const keepIds = new Set(conceptNodes.map((n) => n.id));
  const finalEdges = edges.filter(
    (edge) => keepIds.has(edge.source) && keepIds.has(edge.target),
  );
  return { nodes: conceptNodes, edges: finalEdges };
}

/** Remove Document / Chunk / Keyword path nodes left after structural edge filter. */
export function dropScaffoldingNodes(
  model: OntologyGraphModel,
): OntologyGraphModel {
  const nodes = model.nodes.filter((node) => {
    if (node.kind === "document" || node.kind === "chunk") return false;
    if (isScaffoldingConceptLabel(node.label)) return false;
    const id = node.id.toLowerCase();
    if (id.includes("/keyword/") || id.includes("/chunk/")) return false;
    if (id.includes("documentchunk") || /\/doc\/[^/]+$/.test(id)) {
      // Bare document URIs without concept path segments.
      if (!id.includes("/location/") && !id.includes("/person/") && !id.includes("/org/")) {
        // Keep if label looks conceptual; drop path-like.
        if (isScaffoldingConceptLabel(node.label)) return false;
      }
    }
    return true;
  });
  const keep = new Set(nodes.map((n) => n.id));
  const edges = model.edges.filter(
    (edge) => keep.has(edge.source) && keep.has(edge.target),
  );
  // Drop isolates created by scaffolding removal unless they had SPO edges.
  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  }
  const linked = nodes.filter((node) => (degree.get(node.id) ?? 0) > 0);
  return { nodes: linked.length ? linked : nodes, edges };
}

/**
 * Attach fuse/text importance weights onto a parsed graph using API maps.
 * Matches nodes by label; edges by source-label|predicate|target-label.
 */
export function applyOntologyWeights(
  model: OntologyGraphModel,
  weights?: OntologyWeightMaps | null,
): OntologyGraphModel {
  if (!weights) return model;
  const nodeWeights = weights.nodeWeights ?? {};
  const linkWeights = weights.linkWeights ?? {};
  const hasNodes = Object.keys(nodeWeights).length > 0;
  const hasLinks = Object.keys(linkWeights).length > 0;
  if (!hasNodes && !hasLinks) return model;

  const nodes = model.nodes.map((node) => {
    const key = node.label.trim().toLowerCase();
    const fromMap = nodeWeights[key];
    if (fromMap == null) return node;
    const next =
      node.weight == null ? fromMap : Math.max(node.weight, fromMap);
    return next === node.weight ? node : { ...node, weight: next };
  });
  const labelById = new Map(nodes.map((node) => [node.id, node.label]));

  const edges = model.edges.map((edge) => {
    const sourceLabel = (labelById.get(edge.source) || "").trim().toLowerCase();
    const targetLabel = (labelById.get(edge.target) || "").trim().toLowerCase();
    const pred = (edge.label || "").trim().toLowerCase();
    const key = `${sourceLabel}|${pred}|${targetLabel}`;
    const fromMap = linkWeights[key];
    if (fromMap == null) return edge;
    const next =
      edge.weight == null ? fromMap : Math.max(edge.weight, fromMap);
    return next === edge.weight ? edge : { ...edge, weight: next };
  });

  return { nodes, edges };
}

/**
 * Mark preferred labels as focus without dropping any nodes/edges.
 * Use for analyst-facing comprehensive graphs.
 */
export function markPreferredFocus(
  model: OntologyGraphModel,
  preferredLabels?: string[],
): OntologyGraphModel {
  const preferred = (preferredLabels ?? [])
    .map((label) => label.trim().toLowerCase())
    .filter((label) => label.length >= 2);
  if (!preferred.length) {
    return model;
  }
  return {
    nodes: model.nodes.map((node) => {
      const label = node.label.toLowerCase();
      const hit = preferred.some(
        (needle) => label === needle || label.includes(needle),
      );
      return hit || node.focus ? { ...node, focus: true } : node;
    }),
    edges: model.edges,
  };
}

/**
 * Keep the most relevant ontology nodes for display.
 * - rankBy "relevance" (default): preferred labels + degree + kind
 * - rankBy "degree": highest total links (incoming + outgoing edges)
 * - rankBy "weight": text-importance / fuse weights, then keep linked neighbors
 */
export function pruneOntologyGraph(
  model: OntologyGraphModel,
  options?: {
    preferredLabels?: string[];
    maxNodes?: number;
    rankBy?: "relevance" | "degree" | "weight";
  },
): OntologyGraphModel {
  const maxNodes = options?.maxNodes ?? 28;
  const rankBy = options?.rankBy ?? "relevance";
  if (model.nodes.length === 0) {
    return model;
  }

  const preferred = (options?.preferredLabels ?? [])
    .map((label) => label.trim().toLowerCase())
    .filter((label) => label.length >= 2);

  const withPreferredFocus = (
    nodes: OntologyGraphNode[],
  ): OntologyGraphNode[] =>
    nodes.map((node) => {
      const label = node.label.toLowerCase();
      const preferredHit = preferred.some(
        (needle) => label === needle || label.includes(needle),
      );
      return preferredHit || node.focus ? { ...node, focus: true } : node;
    });

  const inDegree = new Map<string, number>();
  const outDegree = new Map<string, number>();
  const linkStrength = new Map<string, number>();
  for (const edge of model.edges) {
    outDegree.set(edge.source, (outDegree.get(edge.source) ?? 0) + 1);
    inDegree.set(edge.target, (inDegree.get(edge.target) ?? 0) + 1);
    const w = edge.weight ?? 1;
    linkStrength.set(
      edge.source,
      (linkStrength.get(edge.source) ?? 0) + w,
    );
    linkStrength.set(
      edge.target,
      (linkStrength.get(edge.target) ?? 0) + w,
    );
  }
  const totalDegree = (id: string) =>
    (inDegree.get(id) ?? 0) + (outDegree.get(id) ?? 0);

  if (model.nodes.length <= maxNodes) {
    if (rankBy === "degree" || rankBy === "weight") {
      const hubs = [...model.nodes]
        .sort((a, b) => {
          if (rankBy === "weight") {
            return (
              (b.weight ?? 0) - (a.weight ?? 0) ||
              (linkStrength.get(b.id) ?? 0) - (linkStrength.get(a.id) ?? 0) ||
              totalDegree(b.id) - totalDegree(a.id)
            );
          }
          return totalDegree(b.id) - totalDegree(a.id);
        })
        .slice(0, Math.min(3, model.nodes.length));
      const hubIds = new Set(hubs.map((node) => node.id));
      return {
        nodes: model.nodes.map((node) =>
          hubIds.has(node.id) || node.focus ? { ...node, focus: true } : node,
        ),
        edges: [...model.edges].sort(
          (a, b) => (b.weight ?? 1) - (a.weight ?? 1),
        ),
      };
    }
    return preferred.length
      ? { nodes: withPreferredFocus(model.nodes), edges: model.edges }
      : model;
  }

  const scoreNode = (node: OntologyGraphNode): number => {
    const inbound = inDegree.get(node.id) ?? 0;
    const outbound = outDegree.get(node.id) ?? 0;
    const links = inbound + outbound;

    if (rankBy === "weight") {
      let score = (node.weight ?? 0) * 100;
      score += (linkStrength.get(node.id) ?? 0) * 25;
      score += links * 5;
      if (node.focus) score += 50;
      if (node.kind === "literal" || node.kind === "result") score -= 40;
      if (node.kind === "class" || node.kind === "individual") score += 15;
      const label = node.label.toLowerCase();
      for (const needle of preferred) {
        if (label === needle) score += 200;
        else if (label.includes(needle) || needle.includes(label)) score += 80;
      }
      return score;
    }

    if (rankBy === "degree") {
      let score = links * 100;
      score += Math.max(inbound, outbound) * 10;
      if (node.focus) score += 50;
      if (node.kind === "literal" || node.kind === "result") score -= 40;
      if (node.kind === "class" || node.kind === "individual") score += 15;
      return score;
    }

    let score = links;
    if (node.focus) score += 1000;
    const label = node.label.toLowerCase();
    for (const needle of preferred) {
      if (label === needle) score += 600;
      else if (label.includes(needle) || needle.includes(label)) score += 280;
    }
    switch (node.kind) {
      case "class":
        score += 50;
        break;
      case "individual":
        score += 40;
        break;
      case "literal":
        score -= 15;
        break;
      case "result":
        score -= 30;
        break;
      default:
        break;
    }
    return score;
  };

  const ranked = [...model.nodes].sort(
    (a, b) =>
      scoreNode(b) - scoreNode(a) ||
      totalDegree(b.id) - totalDegree(a.id) ||
      a.label.localeCompare(b.label),
  );

  // Reserve ~half the budget for hubs; expand along strongest links.
  const hubBudget =
    rankBy === "weight" || rankBy === "degree"
      ? Math.max(4, Math.floor(maxNodes * 0.55))
      : maxNodes;
  const keep = new Set(ranked.slice(0, hubBudget).map((node) => node.id));

  const seeds =
    rankBy === "degree" || rankBy === "weight"
      ? ranked.slice(0, Math.min(12, ranked.length))
      : ranked
          .filter(
            (node) =>
              node.focus ||
              preferred.some(
                (needle) =>
                  node.label.toLowerCase() === needle ||
                  node.label.toLowerCase().includes(needle),
              ),
          )
          .slice(0, 8);

  const edgesByWeight = [...model.edges].sort(
    (a, b) => (b.weight ?? 1) - (a.weight ?? 1),
  );
  for (const seed of seeds) {
    for (const edge of edgesByWeight) {
      if (keep.size >= maxNodes) break;
      if (edge.source === seed.id) keep.add(edge.target);
      if (edge.target === seed.id) keep.add(edge.source);
    }
  }

  const filtered = model.nodes.filter((node) => keep.has(node.id));
  const nodes =
    rankBy === "degree" || rankBy === "weight"
      ? filtered.map((node) => {
          const rank = ranked.findIndex((item) => item.id === node.id);
          return rank >= 0 && rank < 3
            ? { ...node, focus: true }
            : node;
        })
      : withPreferredFocus(filtered);
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = edgesByWeight.filter(
    (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
  );
  return { nodes, edges };
}

export interface LaidOutNode extends OntologyGraphNode {
  x: number;
  y: number;
}

/** Radial / multi-ring layout: focus (or first) node in the center.
 * Layered mode bands Document → Chunk → concept SPO top-to-bottom.
 */
export function layoutOntologyGraph(
  model: OntologyGraphModel,
  width: number,
  height: number,
  options?: { spacious?: boolean; layered?: boolean },
): { nodes: LaidOutNode[]; edges: OntologyGraphEdge[] } {
  if (model.nodes.length === 0) {
    return { nodes: [], edges: [] };
  }

  const useLayered =
    Boolean(options?.layered) ||
    model.nodes.some(
      (node) => node.kind === "document" || node.kind === "chunk" || node.layer != null,
    );

  if (useLayered) {
    const bands: OntologyGraphNode[][] = [[], [], []];
    for (const node of model.nodes) {
      const layer =
        node.layer ??
        (node.kind === "document" ? 0 : node.kind === "chunk" ? 1 : 2);
      bands[Math.min(2, Math.max(0, layer))].push(node);
    }
    // Shared concepts first within the concept band.
    bands[2].sort(
      (a, b) =>
        Number(b.shared) - Number(a.shared) ||
        (b.weight ?? 0) - (a.weight ?? 0) ||
        a.label.localeCompare(b.label),
    );
    const laid: LaidOutNode[] = [];
    const ys = [height * 0.14, height * 0.38, height * 0.72];
    for (let layer = 0; layer < 3; layer += 1) {
      const group = bands[layer];
      if (!group.length) continue;
      const y = ys[layer];
      group.forEach((node, index) => {
        const x =
          group.length === 1
            ? width / 2
            : (width * (index + 1)) / (group.length + 1);
        // Stagger concept row into two sub-rows when crowded.
        const jitter =
          layer === 2 && group.length > 8
            ? (index % 2 === 0 ? -height * 0.08 : height * 0.08)
            : 0;
        laid.push({ ...node, x, y: y + jitter });
      });
    }
    return { nodes: laid, edges: model.edges };
  }

  const cx = width / 2;
  const cy = height / 2;
  const focus =
    model.nodes.find((node) => node.focus || node.shared) ||
    model.nodes.find((node) => node.kind === "class") ||
    model.nodes[0];
  const others = model.nodes.filter((node) => node.id !== focus.id);
  const spacious = Boolean(options?.spacious);
  const maxR = Math.min(width, height) * (spacious ? 0.46 : 0.42);
  // Spread crowded graphs across rings so labels collide less.
  const perRing = Math.max(
    spacious ? 10 : 8,
    Math.ceil(Math.sqrt(others.length) * (spacious ? 1.8 : 2.2)),
  );
  const ringCount = Math.max(1, Math.ceil(others.length / perRing));
  const laid: LaidOutNode[] = [{ ...focus, x: cx, y: cy }];
  others.forEach((node, index) => {
    const ring = Math.floor(index / perRing);
    const slot = index % perRing;
    const inRing = Math.min(perRing, others.length - ring * perRing);
    const radius = maxR * ((ring + 1) / ringCount);
    const angle = (Math.PI * 2 * slot) / Math.max(inRing, 1) - Math.PI / 2;
    // Slight stagger per ring so spokes don't stack.
    const stagger = ring * 0.18;
    laid.push({
      ...node,
      x: cx + radius * Math.cos(angle + stagger),
      y: cy + radius * Math.sin(angle + stagger),
    });
  });
  return { nodes: laid, edges: model.edges };
}
