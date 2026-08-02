/** Shared helpers for the fused Reporter (Grab + Wiki + Report) workspace. */

import type { FusedOntology, SearchChunkHit } from "@/lib/types";

/** Extract ``## Information`` (or NLP-mangled) block from chunk text. */
export function extractChunkInformation(text: string): {
  narrative: string;
  information: string;
} {
  const raw = (text || "").trim();
  if (!raw) return { narrative: "", information: "" };
  const match =
    /(?:^|\n)\s*(?:#+\s*)+#?\s*Information\b\s*/i.exec(raw) ||
    /(?:^|\s)(?:#+\s*)+#?\s*Information\b\s*/i.exec(raw);
  if (!match || match.index == null) {
    return { narrative: raw, information: "" };
  }
  return {
    narrative: raw.slice(0, match.index).trim(),
    information: raw.slice(match.index + match[0].length).trim(),
  };
}

/**
 * Build wiki agent payload chunks: top-N by score, with ``## Information``
 * from same-parent siblings attached as structured metadata.
 */
export function buildWikiGrabChunks(
  chunks: SearchChunkHit[],
  maxChunks = 8,
): Array<{
  chunk_id: string;
  parent_doc_id: string;
  title: string;
  text_raw: string;
  information: string;
  score: number;
}> {
  const ranked = [...chunks].sort((a, b) => b.score - a.score);
  const selected = ranked.slice(0, maxChunks);
  const infoByParent = new Map<string, string[]>();
  for (const chunk of ranked) {
    const parent = chunk.parent_doc_id || "";
    const { information } = extractChunkInformation(chunk.text_raw || "");
    if (!parent || !information) continue;
    const list = infoByParent.get(parent) ?? [];
    if (!list.includes(information)) list.push(information);
    infoByParent.set(parent, list);
  }
  return selected.map((chunk) => {
    const { narrative, information: ownInfo } = extractChunkInformation(
      chunk.text_raw || "",
    );
    const sibs = infoByParent.get(chunk.parent_doc_id || "") ?? [];
    const parts = [ownInfo, ...sibs].filter(Boolean);
    const unique = [...new Set(parts)];
    const information = unique.join("\n").slice(0, 1400);
    const body = (narrative || chunk.text_raw || "").slice(0, 3500);
    return {
      chunk_id: chunk.chunk_id,
      parent_doc_id: chunk.parent_doc_id,
      title: chunk.title || "",
      text_raw: body,
      information,
      score: chunk.score,
    };
  });
}

/** Status chips shown in the fused Reporter header (not separate screens). */
export const REPORTER_STATUS_STEPS = [
  {
    id: "grab" as const,
    title: "Grab data",
    blurb: "Hybrid search (runs first in Grab & wiki)",
  },
  {
    id: "wiki" as const,
    title: "Persona wiki",
    blurb: "Edit, save to My files, send to commander",
  },
];

export type ReporterStatusStepId = (typeof REPORTER_STATUS_STEPS)[number]["id"];

/** @deprecated Use REPORTER_STATUS_STEPS — kept for any residual imports. */
export type ReporterPhase = 1 | 2 | 3;

/** @deprecated Use REPORTER_STATUS_STEPS */
export const REPORTER_PHASES = REPORTER_STATUS_STEPS.map((step, index) => ({
  id: (index + 1) as ReporterPhase,
  title: step.title,
  blurb: step.blurb,
}));

export const TERMINAL_RUN_STATUSES = new Set([
  "succeeded",
  "failed",
  "blocked",
  "killed",
  "cancelled",
]);

export type AgentRunStep = {
  step_index: number;
  status: string;
  thought_excerpt?: string;
  tool_call?: { name?: string; arguments?: Record<string, unknown> } | null;
  error?: string | null;
};

export type AgentRunHandoff = {
  from_agent: string;
  to_agent: string;
  reason?: string;
  payload_summary?: string;
};

export type AgentRunPayload = {
  run?: {
    run_id?: string;
    status?: string;
    agent?: string;
    workflow?: string | null;
    goal?: string;
    error?: string | null;
    steps_completed?: number;
    delegation_chain?: string[];
    params?: Record<string, unknown>;
    result?: {
      findings?: Array<{ claim: string; chunk_ids?: string[] }>;
      unfilled?: string[];
    } | null;
  };
  steps?: AgentRunStep[];
  handoffs?: AgentRunHandoff[];
  blackboard?: Array<{
    kind?: string;
    builtin?: string;
    bundle_id?: string;
    from?: string;
    to?: string;
    reason?: string;
    chunk_index?: number;
    chunk_total?: number;
    wiki_chars?: number;
    chunk_count?: number;
    mode?: string;
  }>;
  compose_result?: {
    markdown?: string;
    unfilled?: string[];
  } | null;
  budgets?: {
    usage?: {
      llm_tokens?: number;
      tool_calls?: number;
      wall_seconds?: number;
    };
  };
};

/** Human-readable labels for known workflow phase / agent ids. */
const WORKFLOW_PHASE_LABELS: Record<string, string> = {
  scope_bundle: "Scoping an OKF bundle from your query",
  okf_scoped_export: "Exporting grounded evidence into an OKF bundle",
  "builtin:okf_scoped_export": "Exporting grounded evidence into an OKF bundle",
  iterative_wiki: "Folding evidence into a detailed persona wiki",
  okf_iterative_wiki: "Folding evidence into a detailed persona wiki",
  "builtin:okf_iterative_wiki": "Folding evidence into a detailed persona wiki",
  analyse: "Analysing grounded evidence for the wiki",
  review: "Reviewing citations and rejecting ungrounded claims",
  write_wiki: "Writing the OKF wiki page",
  compose: "Composing the report from reviewed findings",
};

const TOOL_LABELS: Record<string, string> = {
  search: "Searching the corpus",
  rag_query: "Running hybrid RAG",
  ontology_query: "Querying the business ontology",
  document_get: "Fetching a source document",
  okf_bundle_get: "Reading the OKF bundle",
  okf_wiki_put: "Saving wiki.md to the OKF bundle",
  workspace_wiki_list: "Listing workspace wikis",
  workspace_wiki_get: "Reading an existing workspace wiki",
};

export type AgentRunActivitySummary = {
  headline: string;
  detail: string | null;
  phaseLabel: string | null;
  agentLabel: string | null;
  toolLabel: string | null;
  stepCount: number;
  recentSteps: AgentRunStep[];
  handoffs: AgentRunHandoff[];
  usage: {
    llm_tokens?: number;
    tool_calls?: number;
    wall_seconds?: number;
  } | null;
};

function labelForAgentOrPhase(id: string | null | undefined): string | null {
  if (!id) return null;
  return WORKFLOW_PHASE_LABELS[id] || null;
}

function workflowPhaseFromReason(reason: string | undefined): string | null {
  if (!reason) return null;
  const match = /workflow:[^:]+:([^\s]+)/.exec(reason);
  return match?.[1] ?? null;
}

function labelForTool(name: string | null | undefined): string | null {
  if (!name) return null;
  return TOOL_LABELS[name] || `Calling tool “${name}”`;
}

/** Derive a short activity description from a live agent run payload. */
export function describeAgentRunActivity(
  payload: AgentRunPayload | null | undefined,
): AgentRunActivitySummary | null {
  if (!payload?.run) return null;
  const status = payload.run.status || "queued";
  const steps = payload.steps ?? [];
  const handoffs = payload.handoffs ?? [];
  const lastStep = steps.length ? steps[steps.length - 1] : null;
  const lastHandoff = handoffs.length ? handoffs[handoffs.length - 1] : null;

  const phaseId =
    workflowPhaseFromReason(lastHandoff?.reason) ||
    payload.run.delegation_chain?.at(-1) ||
    payload.run.agent ||
    null;
  const phaseLabel =
    labelForAgentOrPhase(phaseId) ||
    labelForAgentOrPhase(lastHandoff?.to_agent) ||
    null;
  const agentLabel = payload.run.agent || lastHandoff?.to_agent || null;
  const toolLabel = labelForTool(lastStep?.tool_call?.name);

  let headline: string;
  if (status === "queued") {
    headline = "Queued — waiting for the agent worker…";
  } else if (status === "succeeded") {
    headline = phaseLabel
      ? `Finished — ${phaseLabel.toLowerCase()}`
      : "Agent run succeeded";
  } else if (status === "failed" || status === "blocked" || status === "killed") {
    headline =
      payload.run.error ||
      `Agent run ${status}${lastStep?.error ? `: ${lastStep.error}` : ""}`;
  } else if (status === "cancelled") {
    headline = "Agent run cancelled";
  } else if (toolLabel) {
    headline = toolLabel;
  } else if (phaseLabel) {
    headline = phaseLabel;
  } else if (agentLabel) {
    headline = `Running agent “${agentLabel}”`;
  } else {
    headline = "Agent is working…";
  }

  const thought = lastStep?.thought_excerpt?.trim() || null;
  const handoffSummary = lastHandoff?.payload_summary?.trim() || null;
  const detail =
    thought ||
    (handoffSummary && handoffSummary !== lastHandoff?.to_agent
      ? handoffSummary
      : null);

  return {
    headline,
    detail,
    phaseLabel,
    agentLabel,
    toolLabel,
    stepCount: steps.length,
    recentSteps: steps.slice(-8).reverse(),
    handoffs: handoffs.slice(-6),
    usage: payload.budgets?.usage ?? null,
  };
}

export function errorDetail(body: {
  detail?: string | { detail?: string };
}): string | undefined {
  if (typeof body.detail === "string") {
    return body.detail;
  }
  if (body.detail && typeof body.detail === "object") {
    return body.detail.detail;
  }
  return undefined;
}

export function bundleIdFromRun(payload: AgentRunPayload): string | null {
  const fromParams = payload.run?.params?.bundle_id;
  if (typeof fromParams === "string" && fromParams.trim()) {
    return fromParams.trim();
  }
  for (const entry of payload.blackboard ?? []) {
    if (
      entry.kind === "builtin" &&
      entry.builtin === "okf_scoped_export" &&
      typeof entry.bundle_id === "string" &&
      entry.bundle_id.trim()
    ) {
      return entry.bundle_id.trim();
    }
  }
  return null;
}

export function composeMarkdownFromRun(payload: AgentRunPayload): string {
  return payload.compose_result?.markdown?.trim() || "";
}

/** Recover wiki markdown from a successful okf_wiki_put step on the agent run. */
export function wikiMarkdownFromRun(payload: AgentRunPayload): string | null {
  const steps = [...(payload.steps ?? [])].reverse();
  for (const step of steps) {
    if (step.tool_call?.name !== "okf_wiki_put") continue;
    const markdown = step.tool_call.arguments?.markdown;
    if (typeof markdown === "string" && markdown.trim()) {
      return markdown;
    }
  }
  return null;
}

const CHUNK_ID_RE =
  /chunk_id\s*=\s*([A-Za-z0-9._\-/:]+)|`([A-Za-z0-9._\-/:]+\/[A-Za-z0-9._\-]+)`/gi;

export type WikiEvidenceRefs = {
  chunkIds: string[];
  docIds: string[];
  claimTexts: string[];
};

/** Collect citation / finding ids used to build the wiki (for ontology alignment). */
export function extractWikiEvidenceRefs(
  wikiMarkdown: string,
  payload: AgentRunPayload | null | undefined,
): WikiEvidenceRefs {
  const chunkIds = new Set<string>();
  const docIds = new Set<string>();
  const claimTexts: string[] = [];

  for (const finding of payload?.run?.result?.findings ?? []) {
    const claim = (finding.claim || "").trim();
    if (claim) claimTexts.push(claim);
    for (const cid of finding.chunk_ids ?? []) {
      if (!cid) continue;
      chunkIds.add(cid);
      // Many OSINT ids are parent/source refs (corpus/doc), not Vespa passage ids.
      docIds.add(cid);
      const parent = cid.includes("/") ? cid.split("/").slice(0, -1).join("/") : "";
      if (parent) docIds.add(parent);
      const leaf = cid.includes("/") ? cid.split("/").pop() : cid;
      if (leaf) docIds.add(leaf);
    }
  }

  const text = wikiMarkdown || "";
  for (const match of text.matchAll(CHUNK_ID_RE)) {
    const cid = (match[1] || match[2] || "").trim();
    if (!cid) continue;
    chunkIds.add(cid);
    docIds.add(cid);
  }

  return {
    chunkIds: [...chunkIds],
    docIds: [...docIds],
    claimTexts,
  };
}

function mergeJsonLdDocuments(parts: string[]): string | undefined {
  const nodes: unknown[] = [];
  const pushExpanded = (parsed: unknown) => {
    if (Array.isArray(parsed)) {
      for (const item of parsed) pushExpanded(item);
      return;
    }
    if (!parsed || typeof parsed !== "object") return;
    const obj = parsed as Record<string, unknown>;
    if (Array.isArray(obj["@graph"])) {
      for (const child of obj["@graph"]) pushExpanded(child);
      return;
    }
    if (typeof obj["@id"] === "string") {
      nodes.push(obj);
    }
  };
  for (const part of parts) {
    const raw = (part || "").trim();
    if (!raw) continue;
    try {
      pushExpanded(JSON.parse(raw) as unknown);
    } catch {
      /* skip invalid */
    }
  }
  if (!nodes.length) return undefined;
  return JSON.stringify(nodes);
}

export function mergeOntologyJsonLd(parts: string[]): string | undefined {
  return mergeJsonLdDocuments(parts);
}

/**
 * Union Grab + Wiki fused ontologies for a comprehensive analyst view.
 * Prefer wiki surfaces when labels collide; keep the richer JSON-LD graph.
 */
export function fuseGrabAndWikiOntology(
  grab: FusedOntology | null | undefined,
  wiki: FusedOntology | null | undefined,
): FusedOntology | null {
  if (!grab && !wiki) return null;
  if (!grab) return wiki ?? null;
  if (!wiki) return grab;

  const entitiesByLabel = new Map<string, FusedOntology["entities"][number]>();
  for (const entity of [...grab.entities, ...wiki.entities]) {
    const key = entity.label.trim().toLowerCase();
    if (!key) continue;
    const prev = entitiesByLabel.get(key);
    const chunk_ids = [
      ...new Set([...(prev?.chunk_ids ?? []), ...entity.chunk_ids]),
    ];
    const weight =
      (prev?.weight ?? 0) +
      (entity.weight ?? Math.max(1, entity.chunk_ids.length) * 10);
    const mention_count =
      (prev?.mention_count ?? 0) +
      (entity.mention_count ?? entity.chunk_ids.length);
    const text_hits =
      (prev?.text_hits ?? 0) + (entity.text_hits ?? 0);
    entitiesByLabel.set(key, {
      ...(prev && prev.chunk_ids.length >= entity.chunk_ids.length
        ? prev
        : entity),
      chunk_ids,
      weight,
      mention_count,
      text_hits,
    });
  }

  const keywordsByLabel = new Map<string, FusedOntology["keywords"][number]>();
  for (const keyword of [...grab.keywords, ...wiki.keywords]) {
    const key = keyword.label.trim().toLowerCase();
    if (!key) continue;
    const prev = keywordsByLabel.get(key);
    const chunk_ids = [
      ...new Set([...(prev?.chunk_ids ?? []), ...keyword.chunk_ids]),
    ];
    keywordsByLabel.set(key, {
      ...keyword,
      chunk_ids,
      weight:
        (prev?.weight ?? 0) +
        (keyword.weight ?? Math.max(1, keyword.chunk_ids.length) * 8),
      mention_count:
        (prev?.mention_count ?? 0) +
        (keyword.mention_count ?? keyword.chunk_ids.length),
      text_hits: (prev?.text_hits ?? 0) + (keyword.text_hits ?? 0),
    });
  }

  const relationsByKey = new Map<
    string,
    NonNullable<FusedOntology["relations"]>[number]
  >();
  for (const relation of [
    ...(grab.relations ?? []),
    ...(wiki.relations ?? []),
  ]) {
    const key = [
      relation.source.trim().toLowerCase(),
      relation.predicate.trim().toLowerCase(),
      relation.target.trim().toLowerCase(),
    ].join("|");
    if (!key.replace(/\|/g, "")) continue;
    const prev = relationsByKey.get(key);
    relationsByKey.set(key, {
      source: relation.source,
      predicate: relation.predicate,
      target: relation.target,
      weight: (prev?.weight ?? 0) + (relation.weight ?? 1),
    });
  }

  const json_ld =
    mergeOntologyJsonLd([grab.json_ld || "", wiki.json_ld || ""]) ||
    wiki.json_ld ||
    grab.json_ld ||
    "";

  const documentIds = [
    ...new Set([
      ...(grab.document_ids ?? []),
      ...(wiki.document_ids ?? []),
    ]),
  ];

  return {
    entities: [...entitiesByLabel.values()].sort(
      (a, b) =>
        (b.weight ?? b.chunk_ids.length) - (a.weight ?? a.chunk_ids.length) ||
        a.label.localeCompare(b.label),
    ),
    keywords: [...keywordsByLabel.values()].sort(
      (a, b) =>
        (b.weight ?? b.chunk_ids.length) - (a.weight ?? a.chunk_ids.length) ||
        a.label.localeCompare(b.label),
    ),
    relations: [...relationsByKey.values()].sort(
      (a, b) => b.weight - a.weight,
    ),
    json_ld,
    triple_count: (grab.triple_count ?? 0) + (wiki.triple_count ?? 0) || undefined,
    source_count: Math.max(grab.source_count ?? 0, wiki.source_count ?? 0) || undefined,
    document_ids: documentIds.length ? documentIds : undefined,
    proposed_queries: wiki.proposed_queries?.length
      ? wiki.proposed_queries
      : grab.proposed_queries,
  };
}

/** Prefer ontology nodes that appear in wiki / findings; keep full graph if none match. */
export function alignOntologyToWikiEvidence(
  ontology: FusedOntology | null | undefined,
  wikiMarkdown: string,
  payload: AgentRunPayload | null | undefined,
): FusedOntology | null {
  if (!ontology) return null;
  const refs = extractWikiEvidenceRefs(wikiMarkdown, payload);
  const haystack = [
    wikiMarkdown,
    ...refs.claimTexts,
  ]
    .join("\n")
    .toLowerCase();
  const evidence = new Set(
    [...refs.chunkIds, ...refs.docIds].map((id) => id.toLowerCase()),
  );

  const entityMatches = (label: string, chunkIds: string[]) => {
    const needle = label.trim().toLowerCase();
    if (needle.length >= 3 && haystack.includes(needle)) return true;
    return chunkIds.some((id) => evidence.has(id.toLowerCase()));
  };

  const entities = ontology.entities.filter((entity) =>
    entityMatches(entity.label, entity.chunk_ids),
  );
  const keywords = ontology.keywords.filter((keyword) =>
    entityMatches(keyword.label, keyword.chunk_ids),
  );

  if (!entities.length && !keywords.length) {
    return ontology;
  }
  return {
    ...ontology,
    entities,
    keywords,
    document_ids: refs.docIds.length
      ? refs.docIds
      : ontology.document_ids,
  };
}

export function safeReportFilename(topic: string, reportForm: string): string {
  const stem = topic
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  return `reports/${reportForm}/${stem || "report"}_${stamp}.md`;
}

/** Default My-files directory + filename for a Reporter LLM Wiki save. */
export function suggestedWikiMyFilesTarget(topic: string): {
  directory: string;
  filename: string;
} {
  const stem = topic
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 48);
  return {
    directory: "wiki",
    filename: `${stem || "llm_wiki"}.md`,
  };
}

export async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms));
}
