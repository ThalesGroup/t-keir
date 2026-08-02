"use client";

import { Filter, FileJson, Network, Tag, Wand2, X } from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";

import { OntologyReasonGraph } from "@/components/ontology-reason-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { RagApiError, queryOntologyReasoner } from "@/lib/api";
import { MIN_KEYWORD_LENGTH } from "@/lib/constants";
import {
  groupEntitiesByType,
  type FusedOntology,
  type OntologyReasonerOperation,
  type OntologyReasonerResponse,
  type ProposedOntologyQuery,
  type SemanticEntity,
  type SemanticKeyword,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";

interface OntologySidebarProps {
  ontology: FusedOntology | null;
  loading?: boolean;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
  /** When true, skip outer Card chrome (used inside accordion). */
  embedded?: boolean;
}

type ReasonFamily = "coherence" | "expression" | "sparql";

function EntityButton({
  entity,
  selected,
  onClick,
}: {
  entity: SemanticEntity;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-transparent bg-indigo-100 text-indigo-900 hover:bg-indigo-200 dark:bg-indigo-950 dark:text-indigo-100 dark:hover:bg-indigo-900",
      )}
      title={`${entity.chunk_ids.length} linked chunk(s)`}
    >
      {entity.label}
      <span className="opacity-70">({entity.chunk_ids.length})</span>
    </button>
  );
}

function KeywordButton({
  keyword,
  selected,
  onClick,
}: {
  keyword: SemanticKeyword;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-transparent bg-emerald-100 text-emerald-900 hover:bg-emerald-200 dark:bg-emerald-950 dark:text-emerald-100 dark:hover:bg-emerald-900",
      )}
      title={`${keyword.chunk_ids.length} linked chunk(s)`}
    >
      {keyword.label}
      <span className="opacity-70">({keyword.chunk_ids.length})</span>
    </button>
  );
}

const COHERENCE_OPS: { value: OntologyReasonerOperation; label: string }[] = [
  { value: "consistency", label: "Coherence check" },
  { value: "subclasses", label: "Subclasses" },
  { value: "superclasses", label: "Superclasses" },
  { value: "instances", label: "Instances" },
  { value: "types", label: "Types" },
  { value: "infer", label: "Hierarchy infer" },
];

const DEFAULT_SPARQL = `SELECT ?s ?p ?o WHERE {
  ?s ?p ?o .
} LIMIT 25`;

const DEFAULT_EXPRESSION = "VESSEL";

function ProposalChips({
  items,
  onPick,
}: {
  items: ProposedOntologyQuery[];
  onPick: (item: ProposedOntologyQuery) => void;
}) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <button
          key={`${item.kind}-${item.title}-${item.query.slice(0, 40)}`}
          type="button"
          title={item.description || item.query}
          onClick={() => onPick(item)}
          className="rounded-md border bg-muted/50 px-2 py-1 text-left text-[11px] leading-snug hover:border-primary hover:bg-muted"
        >
          <span className="font-medium">{item.title}</span>
        </button>
      ))}
    </div>
  );
}

export const OntologySidebar = memo(function OntologySidebar({
  ontology,
  loading = false,
  activeChunkIds,
  activeLabel,
  onSelectEntity,
  onSelectKeyword,
  onClearFilter,
  embedded = false,
}: OntologySidebarProps) {
  const { runtimeConfig } = useAuth();
  const entityGroups = useMemo(
    () =>
      ontology
        ? groupEntitiesByType(ontology.entities)
        : new Map<string, SemanticEntity[]>(),
    [ontology],
  );
  const visibleKeywords = useMemo(
    () =>
      ontology
        ? ontology.keywords.filter(
            (keyword) => keyword.label.trim().length >= MIN_KEYWORD_LENGTH,
          )
        : [],
    [ontology],
  );
  const formattedJsonLd = useMemo(() => {
    if (!ontology?.json_ld?.trim()) {
      return "";
    }
    try {
      return JSON.stringify(JSON.parse(ontology.json_ld), null, 2);
    } catch {
      return ontology.json_ld;
    }
  }, [ontology?.json_ld]);

  const proposed = ontology?.proposed_queries ?? [];
  const sparqlProposals = useMemo(
    () => proposed.filter((item) => item.kind === "sparql").slice(0, 3),
    [proposed],
  );
  const expressionProposals = useMemo(
    () => proposed.filter((item) => item.kind === "expression"),
    [proposed],
  );
  const hierarchyProposals = useMemo(
    () =>
      proposed.filter((item) =>
        ["coherence", "subclasses", "superclasses", "instances"].includes(
          item.kind,
        ),
      ),
    [proposed],
  );

  const [family, setFamily] = useState<ReasonFamily>("sparql");
  const [operation, setOperation] =
    useState<OntologyReasonerOperation>("consistency");
  const [classIri, setClassIri] = useState(
    "http://tkeir.local/ontology/DefinedTerm",
  );
  const [individualIri, setIndividualIri] = useState("");
  const [sparql, setSparql] = useState(DEFAULT_SPARQL);
  const [expression, setExpression] = useState(DEFAULT_EXPRESSION);
  const [reasonBusy, setReasonBusy] = useState(false);
  const [reasonError, setReasonError] = useState<string | null>(null);
  const [reasonResult, setReasonResult] =
    useState<OntologyReasonerResponse | null>(null);
  const [resultView, setResultView] = useState<"graph" | "jsonld" | "rows">(
    "rows",
  );

  useEffect(() => {
    if (sparqlProposals[0]?.query) {
      setSparql(sparqlProposals[0].query);
    }
    if (expressionProposals[0]?.query) {
      setExpression(expressionProposals[0].query);
    }
  }, [ontology?.json_ld]); // eslint-disable-line react-hooks/exhaustive-deps -- refresh chips when fused graph changes

  const formattedReasonJsonLd = useMemo(() => {
    const raw = reasonResult?.json_ld?.trim();
    if (!raw) {
      return "";
    }
    try {
      return JSON.stringify(JSON.parse(raw), null, 2);
    } catch {
      return raw;
    }
  }, [reasonResult?.json_ld]);

  const hasFilter = activeChunkIds !== null && activeChunkIds.size > 0;
  const mergeMeta =
    ontology &&
    (ontology.triple_count != null || ontology.source_count != null)
      ? `${ontology.triple_count ?? 0} triples · ${ontology.source_count ?? 0} source graph(s)`
      : null;
  const boDataset =
    runtimeConfig?.businessOntologyDataset?.trim() || "osint";

  async function runReasoner() {
    if (!ontology?.json_ld?.trim()) {
      setReasonError("No fused ontology JSON-LD from the last query.");
      return;
    }
    setReasonBusy(true);
    setReasonError(null);
    try {
      const op: OntologyReasonerOperation | string =
        family === "expression"
          ? "expression"
          : family === "sparql"
            ? "sparql"
            : operation;
      const result = await queryOntologyReasoner(
        {
          json_ld: ontology.json_ld,
          operation: op,
          reasoner: "python",
          class_iri: classIri.trim() || undefined,
          individual_iri: individualIri.trim() || undefined,
          sparql: family === "sparql" ? sparql : undefined,
          expression: family === "expression" ? expression : undefined,
          limit: 50,
        },
        runtimeConfig,
      );
      setReasonResult(result);
      setResultView(
        Array.isArray(result.results) && result.results.length > 0
          ? "rows"
          : "graph",
      );
    } catch (error) {
      setReasonResult(null);
      setReasonError(
        error instanceof RagApiError
          ? error.message
          : error instanceof Error
            ? error.message
            : "Ontology reasoner failed",
      );
    } finally {
      setReasonBusy(false);
    }
  }

  function applyProposal(item: ProposedOntologyQuery) {
    if (item.kind === "sparql") {
      setFamily("sparql");
      setSparql(item.query);
      return;
    }
    if (item.kind === "expression") {
      setFamily("expression");
      setExpression(item.query);
      return;
    }
    if (
      item.kind === "subclasses" ||
      item.kind === "superclasses" ||
      item.kind === "instances"
    ) {
      setFamily("coherence");
      setOperation(item.kind);
      setClassIri(item.query);
      return;
    }
    if (item.kind === "coherence") {
      setFamily("coherence");
      setOperation("consistency");
    }
  }

  return (
    <div
      className={cn(
        embedded
          ? "overflow-hidden"
          : "sticky top-4 h-fit max-h-[calc(100vh-2rem)] overflow-hidden rounded-xl border bg-card text-card-foreground shadow",
      )}
    >
      {!embedded && (
        <div className="flex flex-col space-y-1.5 p-6 pb-3">
          <h3 className="flex items-center gap-2 text-base font-semibold leading-none tracking-tight">
            <Network className="h-5 w-5 text-primary" />
            Ontology Navigator
          </h3>
          {mergeMeta && (
            <p className="text-xs text-muted-foreground">{mergeMeta}</p>
          )}
          {hasFilter && (
            <div className="flex items-center justify-between gap-2 rounded-md bg-muted px-3 py-2 text-xs">
              <span className="flex items-center gap-1 truncate">
                <Filter className="h-3 w-3 shrink-0" />
                <span className="truncate">{activeLabel}</span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={onClearFilter}
              >
                <X className="h-3 w-3" />
                Clear
              </Button>
            </div>
          )}
        </div>
      )}
      {embedded && (
        <div className="mb-3 space-y-2">
          {mergeMeta && (
            <p className="text-xs text-muted-foreground">{mergeMeta}</p>
          )}
          {hasFilter && (
            <div className="flex items-center justify-between gap-2 rounded-md bg-muted px-3 py-2 text-xs">
              <span className="flex items-center gap-1 truncate">
                <Filter className="h-3 w-3 shrink-0" />
                <span className="truncate">{activeLabel}</span>
              </span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2"
                onClick={onClearFilter}
              >
                <X className="h-3 w-3" />
                Clear
              </Button>
            </div>
          )}
        </div>
      )}
      <div className={cn(embedded ? "pb-2" : "p-6 pt-0 pb-6 overflow-y-auto")}>
        {loading ? (
          <p className="text-sm text-muted-foreground">
            Loading ontology for the current search…
          </p>
        ) : !ontology ? (
          <p className="text-sm text-muted-foreground">
            Run a query to load the fused RDF ontology (entities and keywords
            mapped to chunk IDs).
          </p>
        ) : (
          <Tabs defaultValue="entities" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="entities">
                Entities ({ontology.entities.length})
              </TabsTrigger>
              <TabsTrigger value="keywords">
                Keywords ({visibleKeywords.length})
              </TabsTrigger>
              <TabsTrigger value="jsonld">JSON-LD</TabsTrigger>
              <TabsTrigger value="reason">Reason</TabsTrigger>
            </TabsList>

            <TabsContent value="entities" className="mt-4 space-y-4">
              {ontology.entities.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No named entities in this response.
                </p>
              ) : (
                Array.from(entityGroups.entries()).map(([type, entities]) => (
                  <div key={type} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="entity">{type}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {entities.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {entities.map((entity) => (
                        <EntityButton
                          key={`${entity.type}-${entity.label}`}
                          entity={entity}
                          selected={activeLabel === entity.label}
                          onClick={() => onSelectEntity(entity)}
                        />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </TabsContent>

            <TabsContent value="keywords" className="mt-4 space-y-3">
              {visibleKeywords.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No keywords in this response.
                </p>
              ) : (
                <>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Tag className="h-3 w-3" />
                    Click a keyword to highlight linked chunks
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {visibleKeywords.map((keyword) => (
                      <KeywordButton
                        key={keyword.label}
                        keyword={keyword}
                        selected={activeLabel === keyword.label}
                        onClick={() => onSelectKeyword(keyword)}
                      />
                    ))}
                  </div>
                </>
              )}
            </TabsContent>

            <TabsContent value="jsonld" className="mt-4 space-y-3">
              {!formattedJsonLd ? (
                <p className="text-sm text-muted-foreground">
                  No fused JSON-LD graph for this response.
                </p>
              ) : (
                <>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <FileJson className="h-3 w-3" />
                    Fused RDF from analyzed ingest documents + business ontology
                  </div>
                  <pre className="max-h-[50vh] overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed">
                    <code>{formattedJsonLd}</code>
                  </pre>
                </>
              )}
            </TabsContent>

            <TabsContent value="reason" className="mt-4 space-y-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Wand2 className="h-3 w-3" />
                Pure Python reasoner · business ontology: {boDataset}
              </div>

              {sparqlProposals.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[11px] font-medium text-muted-foreground">
                    Suggested SPARQL (from your RAG query)
                  </p>
                  <ProposalChips
                    items={sparqlProposals}
                    onPick={applyProposal}
                  />
                </div>
              )}

              <label className="block space-y-1 text-xs">
                <span className="text-muted-foreground">Request type</span>
                <select
                  className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={family}
                  onChange={(event) =>
                    setFamily(event.target.value as ReasonFamily)
                  }
                >
                  <option value="coherence">
                    A · Coherence / hierarchy
                  </option>
                  <option value="expression">
                    B · Class expression (e.g. Person and age &gt; 20)
                  </option>
                  <option value="sparql">SPARQL SELECT</option>
                </select>
              </label>

              {family === "coherence" && (
                <>
                  {hierarchyProposals.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-medium text-muted-foreground">
                        Ontology hierarchy chips
                      </p>
                      <ProposalChips
                        items={hierarchyProposals}
                        onPick={applyProposal}
                      />
                    </div>
                  )}
                  <label className="block space-y-1 text-xs">
                    <span className="text-muted-foreground">Operation</span>
                    <select
                      className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                      value={operation}
                      onChange={(event) =>
                        setOperation(
                          event.target.value as OntologyReasonerOperation,
                        )
                      }
                    >
                      {COHERENCE_OPS.map((op) => (
                        <option key={op.value} value={op.value}>
                          {op.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {(operation === "subclasses" ||
                    operation === "superclasses" ||
                    operation === "instances") && (
                    <label className="block space-y-1 text-xs">
                      <span className="text-muted-foreground">Class IRI</span>
                      <input
                        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                        value={classIri}
                        onChange={(event) => setClassIri(event.target.value)}
                        placeholder="http://tkeir.local/ontology/Organization"
                      />
                    </label>
                  )}
                  {operation === "types" && (
                    <label className="block space-y-1 text-xs">
                      <span className="text-muted-foreground">
                        Individual IRI
                      </span>
                      <input
                        className="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
                        value={individualIri}
                        onChange={(event) =>
                          setIndividualIri(event.target.value)
                        }
                        placeholder="http://tkeir.local/doc/…"
                      />
                    </label>
                  )}
                </>
              )}

              {family === "expression" && (
                <>
                  {expressionProposals.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-medium text-muted-foreground">
                        Adapted expressions
                      </p>
                      <ProposalChips
                        items={expressionProposals}
                        onPick={applyProposal}
                      />
                    </div>
                  )}
                  <label className="block space-y-1 text-xs">
                    <span className="text-muted-foreground">
                      Expression (Class or Class and prop &gt; N)
                    </span>
                    <textarea
                      className="h-16 w-full rounded-md border bg-background px-2 py-1.5 font-mono text-[11px]"
                      value={expression}
                      onChange={(event) => setExpression(event.target.value)}
                    />
                  </label>
                </>
              )}

              {family === "sparql" && (
                <label className="block space-y-1 text-xs">
                  <span className="text-muted-foreground">SPARQL SELECT</span>
                  <textarea
                    className="h-28 w-full rounded-md border bg-background px-2 py-1.5 font-mono text-[11px]"
                    value={sparql}
                    onChange={(event) => setSparql(event.target.value)}
                  />
                </label>
              )}

              <Button
                type="button"
                size="sm"
                disabled={reasonBusy}
                onClick={() => void runReasoner()}
              >
                {reasonBusy ? "Running…" : "Run ontology query"}
              </Button>
              {reasonError && (
                <p className="text-xs text-destructive">{reasonError}</p>
              )}
              {reasonResult && (
                <div className="space-y-2 text-xs">
                  <p className="text-muted-foreground">
                    {reasonResult.reasoner || "python"} · {reasonResult.backend}
                    {reasonResult.count != null
                      ? ` · ${reasonResult.count} hit(s)`
                      : ""}
                    {reasonResult.note ? ` · ${reasonResult.note}` : ""}
                  </p>
                  {reasonResult.sparql && (
                    <pre className="max-h-24 overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-[10px]">
                      {reasonResult.sparql}
                    </pre>
                  )}
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      size="sm"
                      variant={resultView === "rows" ? "default" : "outline"}
                      className="h-7"
                      onClick={() => setResultView("rows")}
                    >
                      Results
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={resultView === "graph" ? "default" : "outline"}
                      className="h-7"
                      onClick={() => setResultView("graph")}
                    >
                      Graph
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant={resultView === "jsonld" ? "default" : "outline"}
                      className="h-7"
                      onClick={() => setResultView("jsonld")}
                    >
                      JSON-LD
                    </Button>
                  </div>
                  {resultView === "rows" ? (
                    reasonResult.results?.length ? (
                      <div className="max-h-[40vh] overflow-auto rounded-md border">
                        <table className="w-full border-collapse text-left text-[10px]">
                          <thead className="sticky top-0 bg-muted">
                            <tr>
                              {Object.keys(reasonResult.results[0] || {}).map(
                                (key) => (
                                  <th
                                    key={key}
                                    className="border-b px-2 py-1 font-medium"
                                  >
                                    {key}
                                  </th>
                                ),
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {reasonResult.results.map((row, index) => (
                              <tr
                                key={`row-${index}`}
                                className="odd:bg-muted/20"
                              >
                                {Object.keys(reasonResult.results[0] || {}).map(
                                  (key) => (
                                    <td
                                      key={`${index}-${key}`}
                                      className="max-w-[12rem] truncate border-b px-2 py-1 align-top"
                                      title={row[key] || ""}
                                    >
                                      {row[key] || ""}
                                    </td>
                                  ),
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="text-muted-foreground">No tabular rows.</p>
                    )
                  ) : resultView === "graph" ? (
                    <OntologyReasonGraph jsonLd={reasonResult.json_ld} />
                  ) : formattedReasonJsonLd ? (
                    <pre className="max-h-[40vh] overflow-auto rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed">
                      <code>{formattedReasonJsonLd}</code>
                    </pre>
                  ) : (
                    <p className="text-muted-foreground">
                      No JSON-LD payload in this response.
                    </p>
                  )}
                </div>
              )}
            </TabsContent>
          </Tabs>
        )}
      </div>
    </div>
  );
});
