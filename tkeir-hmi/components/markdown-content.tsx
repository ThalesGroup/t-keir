"use client";

import { memo, useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

import { highlightText } from "@/lib/highlight";
import { prepareMarkdownForDisplay } from "@/lib/markdown";
import { cn } from "@/lib/utils";

const REMARK_PLUGINS = [remarkGfm];

function renderHighlighted(
  children: ReactNode,
  entities: string[],
  keywords: string[],
  queryTerms: string[],
): ReactNode {
  if (typeof children === "string") {
    return highlightText(children, entities, keywords, queryTerms);
  }
  if (Array.isArray(children)) {
    return children.map((child, index) => (
      <span key={index}>
        {renderHighlighted(child, entities, keywords, queryTerms)}
      </span>
    ));
  }
  return children;
}

function buildComponents(
  entities: string[],
  keywords: string[],
  queryTerms: string[],
): Components {
  const text = (children: ReactNode) =>
    renderHighlighted(children, entities, keywords, queryTerms);

  return {
    p: ({ children }) => (
      <p className="mb-3 leading-relaxed text-foreground/90 last:mb-0">
        {text(children)}
      </p>
    ),
    h1: ({ children }) => (
      <h1 className="mb-3 mt-4 border-b border-border/60 pb-2 text-base font-semibold tracking-tight first:mt-0">
        {text(children)}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="mb-2 mt-5 text-sm font-semibold tracking-tight text-foreground first:mt-0">
        {text(children)}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="mb-2 mt-3 text-sm font-semibold first:mt-0">
        {text(children)}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="mb-1.5 mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground first:mt-0">
        {text(children)}
      </h4>
    ),
    ul: ({ children }) => (
      <ul className="my-2 list-disc space-y-1.5 pl-5 last:mb-0">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="my-2 list-decimal space-y-1.5 pl-5 last:mb-0">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed text-foreground/90 [&>ul]:mt-1.5 [&>ul]:mb-0">
        {text(children)}
      </li>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-3 border-l-4 border-primary/40 bg-muted/40 py-2 pl-4 italic text-foreground/80">
        {text(children)}
      </blockquote>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-foreground">{text(children)}</strong>
    ),
    em: ({ children }) => <em className="italic">{text(children)}</em>,
    a: ({ href, children }) => (
      <a
        href={href}
        className="font-medium text-primary underline underline-offset-2 hover:text-primary/80"
        target="_blank"
        rel="noreferrer"
      >
        {text(children)}
      </a>
    ),
    hr: () => <hr className="my-4 border-border" />,
    code: ({ className, children, ...props }) => {
      const isBlock = Boolean(className?.includes("language-"));
      if (isBlock) {
        return (
          <code className={cn("font-mono text-[0.8em]", className)} {...props}>
            {children}
          </code>
        );
      }
      return (
        <code
          className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]"
          {...props}
        >
          {children}
        </code>
      );
    },
    pre: ({ children }) => (
      <pre className="my-3 overflow-x-auto rounded-md border bg-muted/50 p-3 text-[0.8em] leading-relaxed">
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="my-3 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-muted/60">{children}</thead>,
    th: ({ children }) => (
      <th className="border border-border px-2 py-1.5 font-semibold">
        {text(children)}
      </th>
    ),
    td: ({ children }) => (
      <td className="border border-border px-2 py-1.5 align-top">
        {text(children)}
      </td>
    ),
  };
}

export interface MarkdownContentProps {
  content: string;
  className?: string;
  highlightEntities?: string[];
  highlightKeywords?: string[];
  highlightQueryTerms?: string[];
}

export const MarkdownContent = memo(function MarkdownContent({
  content,
  className,
  highlightEntities = [],
  highlightKeywords = [],
  highlightQueryTerms = [],
}: MarkdownContentProps) {
  const prepared = useMemo(
    () => prepareMarkdownForDisplay(content),
    [content],
  );
  const components = useMemo(
    () =>
      buildComponents(
        highlightEntities,
        highlightKeywords,
        highlightQueryTerms,
      ),
    [highlightEntities, highlightKeywords, highlightQueryTerms],
  );

  if (!prepared) {
    return null;
  }

  return (
    <div
      className={cn(
        "prose prose-sm max-w-none text-sm leading-relaxed dark:prose-invert",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={components}>
        {prepared}
      </ReactMarkdown>
    </div>
  );
});
