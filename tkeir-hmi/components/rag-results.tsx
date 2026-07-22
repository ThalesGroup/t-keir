"use client";

import { Bot, Network } from "lucide-react";
import { memo, useMemo } from "react";

import { AgentDialog } from "@/components/agent-dialog";
import { AiSynthesis } from "@/components/ai-synthesis";
import { CorrelationIdBadge } from "@/components/correlation-id";
import { DocumentResults } from "@/components/document-results";
import { OntologySidebar } from "@/components/ontology-sidebar";
import { RagReportPanel } from "@/components/rag-report";
import { TechnicalDetails } from "@/components/technical-details";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type {
  QueryResponse,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";

interface RagResultsProps {
  submittedQuery: string;
  response: QueryResponse | null;
  correlationId: string | null;
  loading: boolean;
  agentAvailable: boolean;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
}

export const RagResults = memo(function RagResults({
  submittedQuery,
  response,
  correlationId,
  loading,
  agentAvailable,
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

      <Accordion
        key={submittedQuery || "idle"}
        type="multiple"
        defaultValue={
          agentAvailable
            ? ["ontology", "agent"]
            : response?.ontology
              ? ["ontology"]
              : []
        }
        className="rounded-xl border bg-card px-4 shadow-sm"
      >
        <AccordionItem value="ontology" className="border-b">
          <AccordionTrigger className="text-sm font-medium hover:no-underline">
            <span className="flex items-center gap-2">
              <Network className="h-4 w-4 text-primary" />
              Ontology navigator
              {response?.ontology
                ? ` (${response.ontology.entities.length} entities)`
                : ""}
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <OntologySidebar
              embedded
              ontology={response?.ontology ?? null}
              loading={loading}
              activeChunkIds={activeChunkIds}
              activeLabel={activeLabel}
              onSelectEntity={onSelectEntity}
              onSelectKeyword={onSelectKeyword}
              onClearFilter={onClearFilter}
            />
          </AccordionContent>
        </AccordionItem>

        {agentAvailable && (
          <AccordionItem value="agent" className="border-b-0">
            <AccordionTrigger className="text-sm font-medium hover:no-underline">
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-primary" />
                Agent dialog
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <AgentDialog initialGoal={submittedQuery} />
            </AccordionContent>
          </AccordionItem>
        )}
      </Accordion>

      <TechnicalDetails
        inputPrompt={response?.input_prompt ?? null}
        vespaQuery={response?.vespa_query ?? null}
        loading={loading}
      />
    </>
  );
});
