"use client";

import { FileText, Hash, Layers } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { highlightText } from "@/lib/highlight";
import {
  chunkMatchesFilter,
  groupChunksByDocument,
  type DocumentGroup,
  type RetrievedChunk,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface DocumentResultsProps {
  chunks: RetrievedChunk[];
  loading: boolean;
  activeChunkIds: Set<string> | null;
  highlightEntities?: string[];
  highlightKeywords?: string[];
}

function ChunkBlock({
  chunk,
  highlighted,
  dimmed,
  highlightEntities,
  highlightKeywords,
}: {
  chunk: RetrievedChunk;
  highlighted: boolean;
  dimmed: boolean;
  highlightEntities: string[];
  highlightKeywords: string[];
}) {
  return (
    <div
      id={`chunk-${chunk.chunk_id}`}
      data-chunk-id={chunk.chunk_id}
      className={cn(
        "rounded-lg border bg-muted/30 p-4 transition-all",
        highlighted && "chunk-highlight",
        dimmed && "chunk-dimmed",
      )}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge variant="outline" className="font-mono text-[10px]">
          <Hash className="mr-1 h-3 w-3" />
          {chunk.chunk_id.split("#").pop() ?? chunk.chunk_id}
        </Badge>
        {chunk.relevance !== null && (
          <Badge variant="secondary">
            relevance {(chunk.relevance * 100).toFixed(1)}%
          </Badge>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/90">
        {highlightText(chunk.text_raw, highlightEntities, highlightKeywords)}
      </p>
    </div>
  );
}

function DocumentCard({
  group,
  activeChunkIds,
  defaultOpen,
  highlightEntities,
  highlightKeywords,
}: {
  group: DocumentGroup;
  activeChunkIds: Set<string> | null;
  defaultOpen: boolean;
  highlightEntities: string[];
  highlightKeywords: string[];
}) {
  const visibleChunks = group.chunks.filter((chunk) =>
    chunkMatchesFilter(chunk.chunk_id, activeChunkIds),
  );

  if (activeChunkIds !== null && visibleChunks.length === 0) {
    return null;
  }

  const hasFilter = activeChunkIds !== null && activeChunkIds.size > 0;

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-primary" />
              {group.displayName}
            </CardTitle>
            <p className="break-all font-mono text-xs text-muted-foreground">
              {group.parentDocId}
            </p>
          </div>
          <Badge>
            {hasFilter
              ? `${visibleChunks.length}/${group.chunks.length} chunks`
              : `${group.chunks.length} chunks`}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <Accordion
          type="multiple"
          defaultValue={defaultOpen ? group.chunks.map((c) => c.chunk_id) : []}
          className="w-full"
        >
          {group.chunks.map((chunk) => {
            const isMatch = chunkMatchesFilter(chunk.chunk_id, activeChunkIds);
            const dimmed = hasFilter && !isMatch;
            const highlighted = hasFilter && isMatch;

            return (
              <AccordionItem key={chunk.chunk_id} value={chunk.chunk_id}>
                <AccordionTrigger className="hover:no-underline">
                  <span className="flex items-center gap-2 text-left">
                    <Layers className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate font-mono text-xs">
                      {chunk.chunk_id}
                    </span>
                    {chunk.relevance !== null && (
                      <Badge variant="outline" className="ml-2 shrink-0">
                        {(chunk.relevance * 100).toFixed(1)}%
                      </Badge>
                    )}
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <ChunkBlock
                    chunk={chunk}
                    highlighted={highlighted}
                    dimmed={dimmed}
                    highlightEntities={highlightEntities}
                    highlightKeywords={highlightKeywords}
                  />
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </Accordion>
      </CardContent>
    </Card>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      {[1, 2].map((item) => (
        <Card key={item}>
          <CardHeader>
            <Skeleton className="h-5 w-1/3" />
            <Skeleton className="h-3 w-2/3" />
          </CardHeader>
          <CardContent className="space-y-3">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function DocumentResults({
  chunks,
  loading,
  activeChunkIds,
  highlightEntities = [],
  highlightKeywords = [],
}: DocumentResultsProps) {
  if (loading) {
    return <LoadingSkeleton />;
  }

  if (chunks.length === 0) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No chunks retrieved yet. Run a search to populate document-level and
          chunk-level results.
        </CardContent>
      </Card>
    );
  }

  const groups = groupChunksByDocument(chunks);
  const hasFilter = activeChunkIds !== null && activeChunkIds.size > 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Retrieved Documents & Chunks</h2>
        <Badge variant="secondary">
          {groups.length} document{groups.length === 1 ? "" : "s"} ·{" "}
          {chunks.length} chunk{chunks.length === 1 ? "" : "s"}
          {hasFilter && " (filtered)"}
        </Badge>
      </div>

      {groups.map((group, index) => (
        <DocumentCard
          key={group.parentDocId}
          group={group}
          activeChunkIds={activeChunkIds}
          defaultOpen={index === 0}
          highlightEntities={highlightEntities}
          highlightKeywords={highlightKeywords}
        />
      ))}
    </div>
  );
}
