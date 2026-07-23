"use client";

import { useCallback, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { RagResults } from "@/components/rag-results";
import {
  SearchHeader,
  type SearchParams,
} from "@/components/search-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { queryRag, RagApiError } from "@/lib/api";
import type { OntologyUpdateHandler } from "@/components/ontology-navigator";
import type { QueryResponse } from "@/lib/types";

interface RagPanelProps {
  onOntologyUpdate: OntologyUpdateHandler;
  activeChunkIds: Set<string> | null;
}

export function RagPanel({
  onOntologyUpdate,
  activeChunkIds,
}: RagPanelProps) {
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);

  const handleSearch = useCallback(
    async ({ query, language, hits }: SearchParams) => {
      setLoading(true);
      setError(null);
      setResponse(null);
      setCorrelationId(null);
      setSubmittedQuery(query);
      onOntologyUpdate(null, { loading: true, key: query });

      try {
        const result = await queryRag({ query, language, hits });
        setResponse(result.response);
        setCorrelationId(result.correlationId);
        onOntologyUpdate(result.response.ontology ?? null, {
          loading: false,
          key: query,
        });
      } catch (caught) {
        const message =
          caught instanceof RagApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "An unexpected error occurred.";
        setError(message);
        setResponse(null);
        setCorrelationId(null);
        onOntologyUpdate(null, { loading: false, key: query });
      } finally {
        setLoading(false);
      }
    },
    [onOntologyUpdate],
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h2 className="text-xl font-semibold tracking-tight">RAG report</h2>
        <p className="text-sm text-muted-foreground">
          Retrieve evidence and generate a grounded synthesis report. Ontology
          is shared with Search.
        </p>
      </div>

      <SearchHeader loading={loading} onSearch={handleSearch} />

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Query failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <RagResults
        submittedQuery={submittedQuery}
        response={response}
        correlationId={correlationId}
        loading={loading}
        activeChunkIds={activeChunkIds}
      />
    </div>
  );
}
