"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Layers } from "lucide-react";

import { ReporterChunkCard } from "@/components/reporter-chunk-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { FusedOntology, SearchChunkHit } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ReporterChunkPanelProps {
  chunks: SearchChunkHit[];
  ontology: FusedOntology | null;
  activeChunkIds: Set<string> | null;
  /** When set, only these chunk ids are listed (e.g. wiki citations only). */
  evidenceChunkIds?: Set<string> | null;
  /** Soft-highlight these chunks (e.g. wiki citations) without hiding others. */
  highlightChunkIds?: Set<string> | null;
  defaultOpen?: boolean;
  className?: string;
  title?: string;
}

export function ReporterChunkPanel({
  chunks,
  ontology,
  activeChunkIds,
  evidenceChunkIds = null,
  highlightChunkIds = null,
  defaultOpen = false,
  className,
  title = "Retrieved chunks",
}: ReporterChunkPanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  const filtered = chunks.filter((chunk) => {
    if (evidenceChunkIds && evidenceChunkIds.size > 0) {
      if (!evidenceChunkIds.has(chunk.chunk_id)) return false;
    }
    if (!activeChunkIds || activeChunkIds.size === 0) return true;
    return activeChunkIds.has(chunk.chunk_id);
  });

  const citedCount = highlightChunkIds?.size
    ? filtered.filter((chunk) => highlightChunkIds.has(chunk.chunk_id)).length
    : 0;

  const totalLabel =
    evidenceChunkIds && evidenceChunkIds.size > 0
      ? `${filtered.length} / ${evidenceChunkIds.size} cited`
      : highlightChunkIds && highlightChunkIds.size > 0
        ? `${filtered.length} chunks · ${citedCount} wiki-cited`
        : `${filtered.length} / ${chunks.length}`;

  return (
    <div className={cn("flex flex-col rounded-lg border bg-card", className)}>
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 gap-1.5 px-2"
          onClick={() => setOpen((prev) => !prev)}
          aria-expanded={open}
        >
          {open ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
          <Layers className="h-4 w-4 text-primary" />
          <span className="font-medium">{title}</span>
        </Button>
        <Badge variant="outline" className="tabular-nums">
          {totalLabel}
        </Badge>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {open ? "Hide" : "Show"} search results
        </span>
      </div>

      {open && (
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
          {chunks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No Grab results yet. Run Grab &amp; generate wiki to load search
              chunks for this query.
            </p>
          ) : filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No chunks match the current ontology filter
              {evidenceChunkIds && evidenceChunkIds.size > 0
                ? " / wiki citations"
                : ""}
              .
            </p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((chunk, index) => {
                const cited = Boolean(
                  highlightChunkIds?.has(chunk.chunk_id),
                );
                return (
                  <div key={chunk.chunk_id} className="space-y-1">
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
                      defaultOpen={index === 0 || cited}
                    />
                  </div>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
