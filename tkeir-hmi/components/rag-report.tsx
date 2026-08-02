"use client";

import { memo, useMemo } from "react";
import { Download, FileText } from "lucide-react";

import { MarkdownContent } from "@/components/markdown-content";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { downloadMarkdown, reportFilename } from "@/lib/highlight";

interface RagReportPanelProps {
  query: string;
  reportMarkdown: string | null;
  highlightEntities: string[];
  highlightKeywords: string[];
  highlightQueryTerms: string[];
  loading: boolean;
}

export const RagReportPanel = memo(function RagReportPanel({
  query,
  reportMarkdown,
  highlightEntities,
  highlightKeywords,
  highlightQueryTerms,
  loading,
}: RagReportPanelProps) {
  const hasHighlights = useMemo(
    () =>
      highlightEntities.length > 0 ||
      highlightKeywords.length > 0 ||
      highlightQueryTerms.length > 0,
    [highlightEntities, highlightKeywords, highlightQueryTerms],
  );

  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-5 w-5 text-primary" />
            Detailed Report
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!reportMarkdown?.trim()) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-5 w-5 text-primary" />
            Detailed Report
          </CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Markdown report with highlighted representative entities and keywords
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() =>
            downloadMarkdown(reportFilename(query), reportMarkdown)
          }
        >
          <Download />
          Download .md
        </Button>
      </CardHeader>
      <CardContent>
        {hasHighlights && (
          <div className="mb-4 flex flex-wrap gap-2 text-xs">
            {highlightEntities.slice(0, 8).map((label) => (
              <span
                key={`entity-${label}`}
                className="rounded-full bg-indigo-100 px-2 py-1 font-medium text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100"
              >
                {label}
              </span>
            ))}
            {highlightKeywords.slice(0, 6).map((label) => (
              <span
                key={`keyword-${label}`}
                className="rounded-full bg-emerald-100 px-2 py-1 font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-100"
              >
                {label}
              </span>
            ))}
          </div>
        )}

        <article>
          <MarkdownContent
            content={reportMarkdown}
            highlightEntities={highlightEntities}
            highlightKeywords={highlightKeywords}
            highlightQueryTerms={highlightQueryTerms}
          />
        </article>
      </CardContent>
    </Card>
  );
});
