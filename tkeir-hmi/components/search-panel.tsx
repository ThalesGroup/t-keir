"use client";

import { useCallback, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink, Loader2, Search } from "lucide-react";

import { CorrelationIdBadge } from "@/components/correlation-id";
import type { OntologyUpdateHandler } from "@/components/ontology-navigator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { querySearch, RagApiError } from "@/lib/api";
import {
  formatDocumentName,
  type Language,
  type SearchDocumentHit,
  type SearchResponse,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function snippetForDoc(
  doc: SearchDocumentHit,
  response: SearchResponse,
): string {
  const firstId = doc.chunk_ids[0];
  const chunk = response.chunks.find((item) => item.chunk_id === firstId);
  const text = (chunk?.text_raw || "").replace(/\s+/g, " ").trim();
  if (text.length <= 220) {
    return text;
  }
  return `${text.slice(0, 217)}…`;
}

function docMatchesFilter(
  doc: SearchDocumentHit,
  activeChunkIds: Set<string> | null,
): boolean {
  if (activeChunkIds === null || activeChunkIds.size === 0) {
    return true;
  }
  return doc.chunk_ids.some((id) => activeChunkIds.has(id));
}

interface SearchPanelProps {
  onOntologyUpdate: OntologyUpdateHandler;
  activeChunkIds: Set<string> | null;
}

export function SearchPanel({
  onOntologyUpdate,
  activeChunkIds,
}: SearchPanelProps) {
  const [query, setQuery] = useState("");
  const [language, setLanguage] = useState<Language>("en");
  const [hits, setHits] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [correlationId, setCorrelationId] = useState<string | null>(null);
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const trimmed = query.trim();
      if (!trimmed || loading) {
        return;
      }
      setLoading(true);
      setError(null);
      setSubmitted(trimmed);
      setExpandedDoc(null);
      onOntologyUpdate(null, { loading: true, key: trimmed });
      try {
        const result = await querySearch({
          query: trimmed,
          language,
          hits,
        });
        setResponse(result.response);
        setCorrelationId(result.correlationId);
        onOntologyUpdate(result.response.ontology ?? null, {
          loading: false,
          key: trimmed,
        });
      } catch (caught) {
        const message =
          caught instanceof RagApiError
            ? caught.message
            : caught instanceof Error
              ? caught.message
              : "Search failed.";
        setError(message);
        setResponse(null);
        setCorrelationId(null);
        onOntologyUpdate(null, { loading: false, key: trimmed });
      } finally {
        setLoading(false);
      }
    },
    [hits, language, loading, onOntologyUpdate, query],
  );

  const documents = useMemo(
    () => response?.documents ?? [],
    [response?.documents],
  );

  const showHero = !submitted && !loading;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <form
        onSubmit={handleSubmit}
        className={
          showHero
            ? "flex min-h-[42vh] flex-col items-center justify-center gap-6"
            : "space-y-3"
        }
      >
        {showHero && (
          <div className="text-center">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              T-KEIR Search
            </p>
            <h2 className="mt-1 text-3xl font-semibold tracking-tight sm:text-4xl">
              Search the corpus
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Hybrid retrieval over your documents — ontology is shared with
              RAG.
            </p>
          </div>
        )}

        <div
          className={
            showHero
              ? "flex w-full flex-col gap-3"
              : "flex flex-col gap-3 sm:flex-row sm:items-end"
          }
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search documents…"
              className="h-12 rounded-full border-2 pl-12 text-base shadow-sm"
              disabled={loading}
              autoFocus
            />
          </div>
          {!showHero && (
            <div className="flex gap-2">
              <Select
                value={language}
                onValueChange={(value) => setLanguage(value as Language)}
                disabled={loading}
              >
                <SelectTrigger className="w-[7rem]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">English</SelectItem>
                  <SelectItem value="fr">Français</SelectItem>
                </SelectContent>
              </Select>
              <Button
                type="submit"
                className="h-10 rounded-full px-6"
                disabled={loading || !query.trim()}
              >
                {loading ? <Loader2 className="animate-spin" /> : "Search"}
              </Button>
            </div>
          )}
        </div>

        {showHero && (
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Select
              value={language}
              onValueChange={(value) => setLanguage(value as Language)}
              disabled={loading}
            >
              <SelectTrigger className="w-[8rem]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="fr">Français</SelectItem>
              </SelectContent>
            </Select>
            <Input
              type="number"
              min={1}
              max={100}
              value={hits}
              onChange={(event) => {
                const parsed = Number.parseInt(event.target.value, 10);
                if (!Number.isNaN(parsed)) {
                  setHits(Math.min(100, Math.max(1, parsed)));
                }
              }}
              className="w-24"
              aria-label="Max hits"
              disabled={loading}
            />
            <Button
              type="submit"
              size="lg"
              className="rounded-full px-8"
              disabled={loading || !query.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="animate-spin" />
                  Searching…
                </>
              ) : (
                "Search"
              )}
            </Button>
          </div>
        )}
      </form>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Search failed</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <div className="space-y-4 py-4">
          {[1, 2, 3].map((key) => (
            <div key={key} className="animate-pulse space-y-2">
              <div className="h-4 w-2/3 rounded bg-muted" />
              <div className="h-3 w-full rounded bg-muted" />
              <div className="h-3 w-5/6 rounded bg-muted" />
            </div>
          ))}
        </div>
      )}

      {!loading && correlationId && (
        <CorrelationIdBadge correlationId={correlationId} />
      )}

      {!loading && response && (
        <div className="space-y-1">
          <p className="mb-4 text-sm text-muted-foreground">
            About {documents.length} document
            {documents.length === 1 ? "" : "s"}
            {response.vespa_hits
              ? ` · ${response.vespa_hits} Vespa hits`
              : ""}
            {response.ranking_profile
              ? ` · ${response.ranking_profile}`
              : ""}
            {submitted ? ` for “${submitted}”` : ""}
          </p>
          {response.timings && (
            <p className="mb-4 font-mono text-xs text-muted-foreground">
              timings: nlp {response.timings.nlp_ms.toFixed(0)}ms · vespa{" "}
              {(
                response.timings.vespa_ms ??
                response.timings.vespa_chunk_ms +
                  response.timings.vespa_document_ms
              ).toFixed(0)}
              ms (chunk {response.timings.vespa_chunk_ms.toFixed(0)} · doc{" "}
              {response.timings.vespa_document_ms.toFixed(0)}) · rrf{" "}
              {response.timings.rrf_ms.toFixed(0)}ms · rerank{" "}
              {response.timings.rerank_ms.toFixed(0)}ms
              {response.timings.total_ms != null
                ? ` · total ${response.timings.total_ms.toFixed(0)}ms`
                : ""}
            </p>
          )}

          {documents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents matched.</p>
          ) : (
            <ul className="space-y-6">
              {documents.map((doc) => {
                const title =
                  doc.title?.trim() ||
                  formatDocumentName(doc.document_id);
                const matches = docMatchesFilter(doc, activeChunkIds);
                const filtering =
                  activeChunkIds !== null && activeChunkIds.size > 0;
                const open =
                  expandedDoc === doc.document_id ||
                  (filtering && matches && expandedDoc === null);
                const relatedChunks = response.chunks.filter((chunk) =>
                  doc.chunk_ids.includes(chunk.chunk_id),
                );
                return (
                  <li
                    key={doc.document_id}
                    className={cn(
                      "space-y-1 transition-opacity",
                      filtering && !matches && "opacity-40",
                      filtering && matches && "chunk-highlight rounded-lg p-2",
                    )}
                  >
                    <button
                      type="button"
                      className="group text-left"
                      onClick={() =>
                        setExpandedDoc(
                          expandedDoc === doc.document_id
                            ? null
                            : doc.document_id,
                        )
                      }
                    >
                      <span className="text-lg text-primary group-hover:underline">
                        {title}
                      </span>
                    </button>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span className="truncate font-mono text-[11px]">
                        {doc.document_id}
                      </span>
                      <Badge variant="secondary">
                        score {doc.score.toFixed(3)}
                      </Badge>
                      <Badge variant="outline">
                        {doc.hit_count || doc.chunk_ids.length} chunks
                      </Badge>
                    </div>
                    <p className="text-sm leading-relaxed text-foreground/90">
                      {snippetForDoc(doc, response)}
                    </p>
                    {open && relatedChunks.length > 0 && (
                      <div className="mt-2 space-y-2 rounded-lg border bg-muted/20 p-3">
                        {relatedChunks.map((chunk) => {
                          const chunkActive =
                            activeChunkIds === null ||
                            activeChunkIds.size === 0 ||
                            activeChunkIds.has(chunk.chunk_id);
                          return (
                            <div
                              key={chunk.chunk_id}
                              data-chunk-id={chunk.chunk_id}
                              className={cn(
                                "text-xs",
                                !chunkActive && "opacity-40",
                                chunkActive &&
                                  filtering &&
                                  "rounded border border-primary/40 bg-primary/5 p-2",
                              )}
                            >
                              <div className="mb-1 flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
                                <ExternalLink className="h-3 w-3" />
                                {chunk.chunk_id}
                                <Badge
                                  variant="outline"
                                  className="text-[10px]"
                                >
                                  {chunk.score.toFixed(3)}
                                </Badge>
                              </div>
                              <p className="leading-relaxed text-foreground/80">
                                {chunk.text_raw}
                              </p>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
