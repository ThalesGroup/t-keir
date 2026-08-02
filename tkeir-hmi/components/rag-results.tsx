"use client";

import { Network } from "lucide-react";
import { memo, useMemo } from "react";

import { AiSynthesis } from "@/components/ai-synthesis";
import { CorrelationIdBadge } from "@/components/correlation-id";
import { DocumentResults } from "@/components/document-results";
import { RagReportPanel } from "@/components/rag-report";
import { TechnicalDetails } from "@/components/technical-details";
import type { QueryResponse } from "@/lib/types";

interface RagResultsProps {
  submittedQuery: string;
  response: QueryResponse | null;
  correlationId: string | null;
  loading: boolean;
  activeChunkIds: Set<string> | null;
}

export const RagResults = memo(function RagResults({
  submittedQuery,
  response,
  correlationId,
  loading,
  activeChunkIds,
}: RagResultsProps) {
  const highlightEntities = useMemo(
    () => response?.highlight_entities ?? [],
    [response?.highlight_entities],
  );
  const highlightKeywords = useMemo(
    () => response?.highlight_keywords ?? [],
    [response?.highlight_keywords],
  );
  const highlightQueryTerms = useMemo(
    () => response?.highlight_query_terms ?? [],
    [response?.highlight_query_terms],
  );
  const chunks = useMemo(() => response?.chunks ?? [], [response?.chunks]);

  return (
    <>
      <AiSynthesis
        answer={response?.answer ?? null}
        loading={loading}
        vespaHits={response?.vespa_hits}
        answerUnavailable={response?.answer_unavailable}
      />

      {!loading && correlationId && (
        <CorrelationIdBadge correlationId={correlationId} />
      )}

      <RagReportPanel
        query={submittedQuery}
        reportMarkdown={response?.report_markdown ?? null}
        highlightEntities={highlightEntities}
        highlightKeywords={highlightKeywords}
        highlightQueryTerms={highlightQueryTerms}
        loading={loading}
      />

      <DocumentResults
        chunks={chunks}
        loading={loading}
        activeChunkIds={activeChunkIds}
        highlightEntities={highlightEntities}
        highlightKeywords={highlightKeywords}
        highlightQueryTerms={highlightQueryTerms}
      />

      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Network className="h-3.5 w-3.5" />
        Use the ontology navigator below to filter entities/keywords and
        highlight matching chunks.
      </p>

      <TechnicalDetails
        inputPrompt={response?.input_prompt ?? null}
        vespaQuery={response?.vespa_query ?? null}
        loading={loading}
      />
    </>
  );
});
