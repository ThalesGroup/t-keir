"use client";

import { Badge } from "@/components/ui/badge";
import {
  formatCoveragePct,
  type OntologyCoverage,
} from "@/lib/ontology-coverage";
import { cn } from "@/lib/utils";

interface OntologyCoverageMeterProps {
  coverage: OntologyCoverage;
  title?: string;
  className?: string;
  /** Show matched / missing concept chips (left panel). */
  showDetails?: boolean;
  compact?: boolean;
}

export function OntologyCoverageMeter({
  coverage,
  title = "BO coverage",
  className,
  showDetails = false,
  compact = false,
}: OntologyCoverageMeterProps) {
  if (coverage.total === 0) return null;

  const pct = formatCoveragePct(coverage.ratio);
  const tone =
    coverage.ratio >= 0.6
      ? "bg-emerald-500"
      : coverage.ratio >= 0.3
        ? "bg-amber-500"
        : "bg-rose-500";

  if (compact) {
    return (
      <Badge
        variant="outline"
        className={cn("tabular-nums text-[10px]", className)}
        title={`${coverage.matched}/${coverage.total} external BO concepts hit this surface`}
      >
        {title} {pct}
        <span className="ml-1 text-muted-foreground">
          ({coverage.matched}/{coverage.total})
        </span>
      </Badge>
    );
  }

  return (
    <div className={cn("space-y-2 rounded-md border bg-muted/20 px-3 py-2", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="font-medium">{title}</span>
        <span className="tabular-nums text-muted-foreground">
          {pct} · {coverage.matched}/{coverage.total} concepts
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${Math.min(100, Math.round(coverage.ratio * 100))}%` }}
        />
      </div>
      {showDetails && (
        <div className="space-y-1.5 text-[11px]">
          {coverage.matchedConcepts.length > 0 && (
            <div>
              <p className="mb-1 text-muted-foreground">Matched</p>
              <div className="flex flex-wrap gap-1">
                {coverage.matchedConcepts.slice(0, 12).map((concept) => (
                  <Badge
                    key={concept.conceptId}
                    variant="secondary"
                    className="text-[10px]"
                    title={concept.conceptId}
                  >
                    {concept.preferredLabel}
                  </Badge>
                ))}
                {coverage.matchedConcepts.length > 12 && (
                  <span className="text-muted-foreground">
                    +{coverage.matchedConcepts.length - 12}
                  </span>
                )}
              </div>
            </div>
          )}
          {coverage.missingConcepts.length > 0 && (
            <div>
              <p className="mb-1 text-muted-foreground">Not in fused graph</p>
              <div className="flex flex-wrap gap-1">
                {coverage.missingConcepts.slice(0, 8).map((concept) => (
                  <Badge
                    key={concept.conceptId}
                    variant="outline"
                    className="text-[10px] opacity-70"
                    title={concept.conceptId}
                  >
                    {concept.preferredLabel}
                  </Badge>
                ))}
                {coverage.missingConcepts.length > 8 && (
                  <span className="text-muted-foreground">
                    +{coverage.missingConcepts.length - 8}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
