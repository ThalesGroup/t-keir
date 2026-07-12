"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Download, FileText } from "lucide-react";
import type { Components } from "react-markdown";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  downloadMarkdown,
  highlightText,
  reportFilename,
} from "@/lib/highlight";

interface RagReportPanelProps {
  query: string;
  reportMarkdown: string | null;
  highlightEntities: string[];
  highlightKeywords: string[];
  loading: boolean;
}

function highlightedComponents(
  entities: string[],
  keywords: string[],
): Components {
  const renderChildren = (children: React.ReactNode): React.ReactNode => {
    if (typeof children === "string") {
      return highlightText(children, entities, keywords);
    }
    if (Array.isArray(children)) {
      return children.map((child, index) => (
        <span key={index}>{renderChildren(child)}</span>
      ));
    }
    return children;
  };

  return {
    p: ({ children }) => (
      <p className="mb-3 leading-relaxed last:mb-0">{renderChildren(children)}</p>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed">{renderChildren(children)}</li>
    ),
    h2: ({ children }) => (
      <h2 className="mb-3 mt-6 text-lg font-semibold first:mt-0">
        {renderChildren(children)}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-2 mt-4 text-base font-semibold">
        {renderChildren(children)}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="mb-2 mt-3 text-sm font-semibold">
        {renderChildren(children)}
      </h4>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-3 border-l-4 border-primary/40 bg-muted/40 py-2 pl-4 italic">
        {renderChildren(children)}
      </blockquote>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold">{renderChildren(children)}</strong>
    ),
  };
}

export function RagReportPanel({
  query,
  reportMarkdown,
  highlightEntities,
  highlightKeywords,
  loading,
}: RagReportPanelProps) {
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

        <article className="prose prose-sm max-w-none dark:prose-invert">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={highlightedComponents(
              highlightEntities,
              highlightKeywords,
            )}
          >
            {reportMarkdown}
          </ReactMarkdown>
        </article>
      </CardContent>
    </Card>
  );
}
