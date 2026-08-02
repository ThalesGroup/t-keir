"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Network } from "lucide-react";

import { MarkdownContent } from "@/components/markdown-content";
import { OntologyCoverageMeter } from "@/components/ontology-coverage-meter";
import { OntologyReasonGraph } from "@/components/ontology-reason-graph";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getAnalyzedDocument,
  RagApiError,
  type AnalyzedDocumentPayload,
} from "@/lib/api";
import type { OntologyCoverage } from "@/lib/ontology-coverage";
import type {
  FusedOntology,
  SearchChunkHit,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";

function entitiesForChunk(
  ontology: FusedOntology | null | undefined,
  chunkId: string,
): SemanticEntity[] {
  if (!ontology) return [];
  return ontology.entities.filter((entity) =>
    entity.chunk_ids.includes(chunkId),
  );
}

function keywordsForChunk(
  ontology: FusedOntology | null | undefined,
  chunkId: string,
): SemanticKeyword[] {
  if (!ontology) return [];
  return ontology.keywords.filter((keyword) =>
    keyword.chunk_ids.includes(chunkId),
  );
}

function jsonLdFromAnalyzed(doc: AnalyzedDocumentPayload | null): string {
  const raw = doc?.document_ontology?.json_ld;
  return typeof raw === "string" ? raw : "";
}

function kgText(node: unknown): string {
  if (node == null) return "";
  if (typeof node === "string") return node.trim();
  if (Array.isArray(node)) {
    return node.map((part) => String(part).trim()).filter(Boolean).join(" ");
  }
  if (typeof node === "object") {
    const obj = node as Record<string, unknown>;
    const content = obj.content;
    if (Array.isArray(content)) {
      return content.map((part) => String(part).trim()).filter(Boolean).join(" ");
    }
    if (typeof content === "string") return content.trim();
  }
  return "";
}

/** Build SPO relations from analyzed ``kg`` for the chunk graph. */
function spoFromAnalyzed(
  doc: AnalyzedDocumentPayload | null,
): Array<{ source: string; predicate: string; target: string; weight: number }> {
  const kg = (doc as { kg?: unknown } | null)?.kg;
  if (!Array.isArray(kg)) return [];
  const out: Array<{
    source: string;
    predicate: string;
    target: string;
    weight: number;
  }> = [];
  for (const triple of kg) {
    if (!triple || typeof triple !== "object") continue;
    const row = triple as Record<string, unknown>;
    if (String(row.field_type || "") === "keywords") continue;
    const source = kgText(row.subject);
    const predicate = kgText(row.property);
    const target = kgText(row.value);
    if (!source || !predicate) continue;
    out.push({ source, predicate, target, weight: 3 });
  }
  return out;
}

interface ReporterChunkCardProps {
  chunk: SearchChunkHit;
  ontology: FusedOntology | null;
  active: boolean;
  defaultOpen?: boolean;
  /** Heading above the per-doc/chunk ontology graph. */
  ontologyTitle?: string;
  /** External business-ontology coverage for this chunk. */
  boCoverage?: OntologyCoverage | null;
}

export function ReporterChunkCard({
  chunk,
  ontology,
  active,
  defaultOpen = false,
  ontologyTitle = "Analyzed ontology graph",
  boCoverage = null,
}: ReporterChunkCardProps) {
  const { runtimeConfig } = useAuth();
  const [open, setOpen] = useState(defaultOpen);
  const [loadingOnt, setLoadingOnt] = useState(false);
  const [analyzed, setAnalyzed] = useState<AnalyzedDocumentPayload | null>(
    null,
  );
  const [ontError, setOntError] = useState<string | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  const linkedEntities = useMemo(
    () => entitiesForChunk(ontology, chunk.chunk_id),
    [ontology, chunk.chunk_id],
  );
  const linkedKeywords = useMemo(
    () => keywordsForChunk(ontology, chunk.chunk_id),
    [ontology, chunk.chunk_id],
  );

  useEffect(() => {
    if (!open) return;
    const sourceRef = chunk.parent_doc_id;
    if (!sourceRef || loadedFor === sourceRef) return;
    let cancelled = false;
    setLoadingOnt(true);
    setOntError(null);
    void getAnalyzedDocument(sourceRef, runtimeConfig)
      .then((payload) => {
        if (cancelled) return;
        setAnalyzed(payload);
        setLoadedFor(sourceRef);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message =
          err instanceof RagApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : "Failed to load analyzed ontology";
        setOntError(message);
        setAnalyzed(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingOnt(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, chunk.parent_doc_id, loadedFor, runtimeConfig]);

  const jsonLd = jsonLdFromAnalyzed(analyzed);
  const kgRelations = useMemo(() => spoFromAnalyzed(analyzed), [analyzed]);
  const chunkOntology = useMemo(
    () => ({
      entities: linkedEntities,
      keywords: linkedKeywords,
      relations: kgRelations,
      json_ld: jsonLd,
      document_ids: chunk.parent_doc_id ? [chunk.parent_doc_id] : [],
      chunks: [
        {
          chunk_id: chunk.chunk_id,
          parent_doc_id: chunk.parent_doc_id,
        },
      ],
    }),
    [
      linkedEntities,
      linkedKeywords,
      kgRelations,
      jsonLd,
      chunk.chunk_id,
      chunk.parent_doc_id,
    ],
  );

  return (
    <li
      data-chunk-id={chunk.chunk_id}
      className={cn(
        "rounded-lg border bg-card/40 transition-opacity",
        !active && "opacity-40",
        active && "border-primary/30",
      )}
    >
      <button
        type="button"
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium">
              {chunk.title?.trim() ||
                chunk.parent_doc_id.split("/").pop() ||
                chunk.chunk_id}
            </span>
            <Badge variant="outline" className="font-mono text-[10px]">
              {chunk.score.toFixed(3)}
            </Badge>
            {(linkedEntities.length > 0 || linkedKeywords.length > 0) && (
              <Badge variant="secondary" className="text-[10px]">
                <Network className="mr-1 h-3 w-3" />
                {linkedEntities.length} ent · {linkedKeywords.length} kw
              </Badge>
            )}
            {boCoverage && boCoverage.total > 0 && (
              <OntologyCoverageMeter
                coverage={boCoverage}
                title="BO"
                compact
              />
            )}
          </div>
          <p className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground">
            {chunk.chunk_id}
          </p>
          {!open && (
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {chunk.text_raw.replace(/\s+/g, " ").trim().slice(0, 220)}
            </p>
          )}
        </div>
      </button>

      {open && (
        <div className="space-y-3 border-t px-3 py-3">
          <div className="rounded-md border bg-background/80 p-3">
            <MarkdownContent
              content={chunk.text_raw}
              className="text-[13px] [&_h1]:text-sm [&_h2]:text-[13px] [&_li]:text-[13px] [&_p]:mb-2 [&_p]:text-[13px]"
            />
          </div>

          {(linkedEntities.length > 0 || linkedKeywords.length > 0) && (
            <div className="flex flex-wrap gap-1.5">
              {linkedEntities.map((entity) => (
                <Badge
                  key={`e-${entity.label}-${entity.type}`}
                  variant="outline"
                  className="text-[10px]"
                  title={entity.type}
                >
                  {entity.label}
                </Badge>
              ))}
              {linkedKeywords.map((keyword) => (
                <Badge
                  key={`k-${keyword.label}`}
                  variant="secondary"
                  className="text-[10px]"
                >
                  {keyword.label}
                </Badge>
              ))}
            </div>
          )}

          {boCoverage && boCoverage.total > 0 && (
            <OntologyCoverageMeter
              coverage={boCoverage}
              title="External BO coverage on this chunk"
              showDetails
            />
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <Network className="h-3.5 w-3.5" />
              {ontologyTitle}
              {analyzed?.document_ontology?.shacl_status ? (
                <Badge variant="outline" className="text-[10px]">
                  {String(analyzed.document_ontology.shacl_status)}
                </Badge>
              ) : null}
            </div>
            {loadingOnt && (
              <p className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading analyzed_document.json for{" "}
                <code className="truncate">{chunk.parent_doc_id}</code>
              </p>
            )}
            {ontError && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {ontError}
              </p>
            )}
            {!loadingOnt && !ontError && (jsonLd || kgRelations.length > 0) && (
              <OntologyReasonGraph
                jsonLd={jsonLd || "[]"}
                ontology={chunkOntology}
                chunks={chunkOntology.chunks}
                relations={kgRelations}
                maxNodes={36}
                rankBy="weight"
                width={520}
                height={320}
                className="w-full"
                title={`Analyzed SPO — ${chunk.parent_doc_id}`}
                expandable
              />
            )}
            {!loadingOnt && !ontError && !jsonLd && kgRelations.length === 0 && analyzed && (
              <p className="text-xs text-muted-foreground">
                Analyzed document has no kg SPO / document_ontology.json_ld.
              </p>
            )}
            {!loadingOnt && !analyzed && !ontError && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setLoadedFor(null)}
              >
                Retry ontology load
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}
