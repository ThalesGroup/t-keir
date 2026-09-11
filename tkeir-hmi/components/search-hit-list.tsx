"use client";

import { FileText } from "lucide-react";
import { useMemo } from "react";

import { DocumentPlacesMap } from "@/components/document-places-map";
import { ReporterChunkCard } from "@/components/reporter-chunk-card";
import { Badge } from "@/components/ui/badge";
import {
  collectLocationCandidates,
  locationsForDocument,
} from "@/lib/document-locations";
import type { OntologyCoverage } from "@/lib/ontology-coverage";
import {
  displayPassageTitle,
  explicitChunkTitle,
  groupSearchHits,
  matchStrength,
} from "@/lib/search-display";
import type {
  FusedOntology,
  SearchChunkHit,
  SearchDocumentHit,
} from "@/lib/types";

function scrollToChunk(chunkIds: string[]) {
  const chunkId = chunkIds[0];
  if (!chunkId) return;
  const element = document.querySelector(
    `[data-chunk-id="${CSS.escape(chunkId)}"]`,
  );
  element?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function entityLabelsForChunk(
  ontology: FusedOntology | null,
  chunkId: string,
): string[] {
  if (!ontology) return [];
  return [...ontology.entities]
    .filter((entity) => entity.chunk_ids.includes(chunkId))
    .sort(
      (a, b) =>
        (b.weight ?? b.chunk_ids.length) - (a.weight ?? a.chunk_ids.length),
    )
    .map((entity) => entity.label.trim())
    .filter(Boolean)
    .slice(0, 3);
}

interface SearchHitListProps {
  chunks: SearchChunkHit[];
  documents?: SearchDocumentHit[];
  ontology: FusedOntology | null;
  activeChunkIds?: Set<string> | null;
  highlightChunkIds?: Set<string> | null;
  chunkCoverageById?: Map<string, OntologyCoverage> | null;
  ontologyTitle?: string;
}

export function SearchHitList({
  chunks,
  documents = [],
  ontology,
  activeChunkIds = null,
  highlightChunkIds = null,
  chunkCoverageById = null,
  ontologyTitle = "Chunk ontology",
}: SearchHitListProps) {
  const groups = useMemo(
    () => groupSearchHits(chunks, documents),
    [chunks, documents],
  );
  const placeCandidates = useMemo(
    () => collectLocationCandidates(ontology, chunks),
    [ontology, chunks],
  );
  const rankByChunkId = useMemo(() => {
    const ranks = new Map<string, number>();
    let next = 0;
    for (const group of groups) {
      for (const chunk of group.chunks) {
        next += 1;
        ranks.set(chunk.chunk_id, next);
      }
    }
    return ranks;
  }, [groups]);
  const docsWithPlaces = groups.filter(
    (group) =>
      locationsForDocument(placeCandidates, group.parentDocId).length > 0,
  ).length;
  const maxScore = chunks.reduce(
    (max, chunk) => Math.max(max, chunk.score || 0),
    0,
  );

  return (
    <div className="space-y-3">
      {docsWithPlaces > 1 && (
        <DocumentPlacesMap
          candidates={placeCandidates}
          title="Where these documents take place"
          onSelectChunkIds={scrollToChunk}
        />
      )}
      {groups.map((group) => {
        const nested = group.chunks.length > 1;
        const docPlaces = locationsForDocument(
          placeCandidates,
          group.parentDocId,
        );
        const docMap =
          docPlaces.length > 0 ? (
            <DocumentPlacesMap
              candidates={docPlaces}
              title="Places in this document"
              onSelectChunkIds={scrollToChunk}
            />
          ) : null;
        if (!nested) {
          const chunk = group.chunks[0];
          const rank = rankByChunkId.get(chunk.chunk_id) ?? 1;
          const cited = Boolean(highlightChunkIds?.has(chunk.chunk_id));
          const entityLabels = entityLabelsForChunk(ontology, chunk.chunk_id);
          return (
            <div key={group.parentDocId} className="space-y-2">
              {docMap}
              {cited && (
                <Badge
                  variant="outline"
                  className="border-primary/40 text-[10px] text-primary"
                >
                  wiki citation
                </Badge>
              )}
              <ReporterChunkCard
                chunk={chunk}
                ontology={ontology}
                active={
                  !activeChunkIds ||
                  activeChunkIds.size === 0 ||
                  activeChunkIds.has(chunk.chunk_id)
                }
                defaultOpen={rank === 1 || cited}
                ontologyTitle={ontologyTitle}
                boCoverage={chunkCoverageById?.get(chunk.chunk_id) ?? null}
                displayTitle={explicitChunkTitle(chunk, {
                  documentTitle: group.title,
                  entityLabels,
                })}
                showSource
                rank={rank}
                strength={matchStrength(chunk.score, maxScore)}
              />
            </div>
          );
        }
        return (
          <section
            key={group.parentDocId}
            className="overflow-hidden rounded-lg border bg-card/60"
          >
            <header className="flex items-start gap-2 border-b bg-muted/30 px-3 py-2.5">
              <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <h3 className="break-words text-sm font-semibold leading-snug tracking-tight">
                  {group.title}
                </h3>
                {group.sourceLabel &&
                  group.sourceLabel.localeCompare(group.title, undefined, {
                    sensitivity: "accent",
                  }) !== 0 && (
                    <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                      {group.sourceLabel}
                    </p>
                  )}
              </div>
              <Badge variant="secondary" className="shrink-0 tabular-nums">
                {group.chunks.length} passages
              </Badge>
            </header>
            {docMap ? <div className="px-2 pt-2">{docMap}</div> : null}
            <ul className="space-y-2 p-2">
              {group.chunks.map((chunk, index) => {
                const rank = rankByChunkId.get(chunk.chunk_id) ?? 1;
                const cited = Boolean(highlightChunkIds?.has(chunk.chunk_id));
                const entityLabels = entityLabelsForChunk(
                  ontology,
                  chunk.chunk_id,
                );
                return (
                  <li key={chunk.chunk_id} className="space-y-1">
                    {cited && (
                      <Badge
                        variant="outline"
                        className="border-primary/40 text-[10px] text-primary"
                      >
                        wiki citation
                      </Badge>
                    )}
                    <ReporterChunkCard
                      chunk={chunk}
                      ontology={ontology}
                      active={
                        !activeChunkIds ||
                        activeChunkIds.size === 0 ||
                        activeChunkIds.has(chunk.chunk_id)
                      }
                      defaultOpen={rank === 1 || cited}
                      ontologyTitle={ontologyTitle}
                      boCoverage={
                        chunkCoverageById?.get(chunk.chunk_id) ?? null
                      }
                      displayTitle={displayPassageTitle(
                        chunk,
                        group.title,
                        index,
                        entityLabels,
                      )}
                      showSource={false}
                      rank={rank}
                      strength={matchStrength(chunk.score, maxScore)}
                      nested
                    />
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
