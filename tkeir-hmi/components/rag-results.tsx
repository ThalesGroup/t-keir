"use client";

import { memo, useMemo } from "react";

import { AiSynthesis } from "@/components/ai-synthesis";
import { DocumentResults } from "@/components/document-results";
import { InputPromptPanel } from "@/components/input-prompt-panel";
import { VespaQueryPanel } from "@/components/vespa-query-panel";
import { OntologySidebar } from "@/components/ontology-sidebar";
import { RagReportPanel } from "@/components/rag-report";
import type {
  QueryResponse,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";

interface RagResultsProps {
  submittedQuery: string;
  response: QueryResponse | null;
  loading: boolean;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
}

export const RagResults = memo(function RagResults({
  submittedQuery,
  response,
  loading,
  activeChunkIds,
  activeLabel,
  onSelectEntity,
  onSelectKeyword,
  onClearFilter,
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

      <InputPromptPanel
        inputPrompt={response?.input_prompt ?? null}
        loading={loading}
      />

      <VespaQueryPanel
        vespaQuery={response?.vespa_query ?? null}
        loading={loading}
      />

      <RagReportPanel
        query={submittedQuery}
        reportMarkdown={response?.report_markdown ?? null}
        highlightEntities={highlightEntities}
        highlightKeywords={highlightKeywords}
        highlightQueryTerms={highlightQueryTerms}
        loading={loading}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem] xl:grid-cols-[1fr_22rem]">
        <DocumentResults
          chunks={chunks}
          loading={loading}
          activeChunkIds={activeChunkIds}
          highlightEntities={highlightEntities}
          highlightKeywords={highlightKeywords}
          highlightQueryTerms={highlightQueryTerms}
        />

        <OntologySidebar
          ontology={response?.ontology ?? null}
          loading={loading}
          activeChunkIds={activeChunkIds}
          activeLabel={activeLabel}
          onSelectEntity={onSelectEntity}
          onSelectKeyword={onSelectKeyword}
          onClearFilter={onClearFilter}
        />
      </div>
    </>
  );
});
