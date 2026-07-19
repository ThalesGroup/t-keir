"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Moon, Sun } from "lucide-react";

import { RagResults } from "@/components/rag-results";
import {
  SearchHeader,
  type SearchParams,
} from "@/components/search-header";
import { AuthButton } from "@/components/auth-button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { checkHealth, queryRag, RagApiError } from "@/lib/api";
import type { QueryResponse, SemanticEntity, SemanticKeyword } from "@/lib/types";

export function RagDashboard() {
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null);
  const [activeChunkIds, setActiveChunkIds] = useState<Set<string> | null>(
    null,
  );
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    void checkHealth().then(setApiHealthy);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  const scrollToFirstMatch = useCallback((chunkIds: string[]) => {
    if (chunkIds.length === 0) {
      return;
    }
    const element = document.querySelector(
      `[data-chunk-id="${CSS.escape(chunkIds[0])}"]`,
    );
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const handleSearch = useCallback(async ({ query, language, hits }: SearchParams) => {
    setLoading(true);
    setError(null);
    setResponse(null);
    setCorrelationId(null);
    setSubmittedQuery(query);
    setActiveChunkIds(null);
    setActiveLabel(null);

    try {
      const result = await queryRag({ query, language, hits });
      setResponse(result.response);
      setCorrelationId(result.correlationId);
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
    } finally {
      setLoading(false);
    }
  }, []);

  const handleSelectEntity = useCallback(
    (entity: SemanticEntity) => {
      if (activeLabel === entity.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      const ids = new Set(entity.chunk_ids);
      setActiveChunkIds(ids);
      setActiveLabel(entity.label);
      scrollToFirstMatch(entity.chunk_ids);
    },
    [activeLabel, scrollToFirstMatch],
  );

  const handleSelectKeyword = useCallback(
    (keyword: SemanticKeyword) => {
      if (activeLabel === keyword.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      const ids = new Set(keyword.chunk_ids);
      setActiveChunkIds(ids);
      setActiveLabel(keyword.label);
      scrollToFirstMatch(keyword.chunk_ids);
    },
    [activeLabel, scrollToFirstMatch],
  );

  const handleClearFilter = useCallback(() => {
    setActiveChunkIds(null);
    setActiveLabel(null);
  }, []);

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              T-KEIR
            </p>
            <h1 className="text-xl font-bold tracking-tight">
              Search & RAG Interface
            </h1>
            <p className="text-sm text-muted-foreground">
              Two-level retrieval — documents & chunks with fused ontology
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="/agents"
              className="text-sm text-muted-foreground underline-offset-2 hover:underline"
            >
              Agents
            </a>
            <a
              href="/admin"
              className="text-sm text-muted-foreground underline-offset-2 hover:underline"
            >
              Admin
            </a>
            <AuthButton />
            <Button
              variant="outline"
              size="icon"
              onClick={() => setDarkMode((value) => !value)}
              aria-label="Toggle dark mode"
            >
              {darkMode ? <Sun /> : <Moon />}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        {apiHealthy === false && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>RAG API unreachable</AlertTitle>
            <AlertDescription>
              Start the FastAPI server with{" "}
              <code className="rounded bg-muted px-1 py-0.5 text-xs">
                make rag
              </code>{" "}
              (default port 8090).
            </AlertDescription>
          </Alert>
        )}

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
          activeLabel={activeLabel}
          onSelectEntity={handleSelectEntity}
          onSelectKeyword={handleSelectKeyword}
          onClearFilter={handleClearFilter}
        />
      </main>
    </div>
  );
}
