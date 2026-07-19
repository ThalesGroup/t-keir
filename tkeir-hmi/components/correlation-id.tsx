"use client";

import { useCallback, useState } from "react";
import { Check, Copy, Fingerprint } from "lucide-react";

import { Button } from "@/components/ui/button";

interface CorrelationIdBadgeProps {
  correlationId: string | null;
  auditBaseUrl?: string;
}

/** Shows X-Correlation-Id with copy + optional audit deep-link. */
export function CorrelationIdBadge({
  correlationId,
  auditBaseUrl = "/admin",
}: CorrelationIdBadgeProps) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(async () => {
    if (!correlationId) {
      return;
    }
    try {
      await navigator.clipboard.writeText(correlationId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }, [correlationId]);

  if (!correlationId) {
    return null;
  }

  const auditHref = `${auditBaseUrl}?correlation_id=${encodeURIComponent(correlationId)}`;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Fingerprint className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span className="font-medium">Correlation ID</span>
      <code className="max-w-[14rem] truncate rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] sm:max-w-none">
        {correlationId}
      </code>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        className="h-7 px-2"
        onClick={() => void onCopy()}
        aria-label="Copy correlation ID"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-green-600" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
      </Button>
      <a
        href={auditHref}
        className="underline-offset-2 hover:underline"
        title="Open oversight panel for this correlation ID"
      >
        Audit this answer
      </a>
    </div>
  );
}
