"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Moon, Sun } from "lucide-react";

import { AiSynthesis } from "@/components/ai-synthesis";
import { DocumentResults } from "@/components/document-results";
import { OntologySidebar } from "@/components/ontology-sidebar";
import { RagReportPanel } from "@/components/rag-report";
import { SearchHeader } from "@/components/search-header";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { checkHealth, queryRag, RagApiError } from "@/lib/api";
import type {
  Language,
  QueryResponse,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";

export function RagDashboard() {
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [hits, setHits] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
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

  const runSearch = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      return;
    }

    setLoading(true);
    setError(null);
    setActiveChunkIds(null);
    setActiveLabel(null);

    try {
      const result = await queryRag({
        query: trimmed,
        language,
        hits,
      });
      setResponse(result);
    } catch (caught) {
      const message =
        caught instanceof RagApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "An unexpected error occurred.";
      setError(message);
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, [query, language, hits]);

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
          <Button
            variant="outline"
            size="icon"
            onClick={() => setDarkMode((value) => !value)}
            aria-label="Toggle dark mode"
          >
            {darkMode ? <Sun /> : <Moon />}
          </Button>
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
                cd vespa &amp;&amp; make rag
              </code>{" "}
              (default port 8090).
            </AlertDescription>
          </Alert>
        )}

        <SearchHeader
          query={query}
          language={language}
          hits={hits}
          loading={loading}
          onQueryChange={setQuery}
          onLanguageChange={setLanguage}
          onHitsChange={setHits}
          onSubmit={() => void runSearch()}
        />

        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>Query failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <AiSynthesis
          answer={response?.answer ?? null}
          loading={loading}
          vespaHits={response?.vespa_hits}
        />

        <RagReportPanel
          query={query}
          reportMarkdown={response?.report_markdown ?? null}
          highlightEntities={response?.highlight_entities ?? []}
          highlightKeywords={response?.highlight_keywords ?? []}
          loading={loading}
        />

        <div className="grid gap-6 lg:grid-cols-[1fr_20rem] xl:grid-cols-[1fr_22rem]">
          <DocumentResults
            chunks={response?.chunks ?? []}
            loading={loading}
            activeChunkIds={activeChunkIds}
            highlightEntities={response?.highlight_entities ?? []}
            highlightKeywords={response?.highlight_keywords ?? []}
          />

          <OntologySidebar
            ontology={response?.ontology ?? null}
            activeChunkIds={activeChunkIds}
            activeLabel={activeLabel}
            onSelectEntity={handleSelectEntity}
            onSelectKeyword={handleSelectKeyword}
            onClearFilter={() => {
              setActiveChunkIds(null);
              setActiveLabel(null);
            }}
          />
        </div>
      </main>
    </div>
  );
}
