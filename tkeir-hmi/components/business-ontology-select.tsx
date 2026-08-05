"use client";

import {
  BUSINESS_ONTOLOGY_DATASETS,
  resolveBusinessOntologyDataset,
} from "@/lib/business-ontology-datasets";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type BusinessOntologySelectProps = {
  value: string;
  onChange: (dataset: string) => void;
  disabled?: boolean;
  /** Compact label above the control (default: Business ontology). */
  label?: string;
  className?: string;
  triggerClassName?: string;
  /** When true, omit the field legend (caller supplies its own). */
  hideLabel?: boolean;
};

/**
 * Dropdown for ``datasets/<id>/business_ontology.yaml`` used at ingest / reporter.
 */
export function BusinessOntologySelect({
  value,
  onChange,
  disabled,
  label = "Business ontology",
  className,
  triggerClassName,
  hideLabel,
}: BusinessOntologySelectProps) {
  const resolved = resolveBusinessOntologyDataset(undefined, value);
  const known = BUSINESS_ONTOLOGY_DATASETS.some((d) => d.id === resolved);
  const options = known
    ? BUSINESS_ONTOLOGY_DATASETS
    : [
        {
          id: resolved,
          label: resolved,
          description: "Configured dataset",
        },
        ...BUSINESS_ONTOLOGY_DATASETS,
      ];

  return (
    <label className={cn("flex flex-col gap-1 text-xs text-muted-foreground", className)}>
      {hideLabel ? null : <span>{label}</span>}
      <Select
        value={resolved}
        onValueChange={onChange}
        disabled={disabled}
      >
        <SelectTrigger
          className={cn("h-9 min-w-[10rem] bg-background", triggerClassName)}
          aria-label={label}
        >
          <SelectValue placeholder="Select ontology" />
        </SelectTrigger>
        <SelectContent>
          {options.map((opt) => (
            <SelectItem key={opt.id} value={opt.id}>
              <span className="flex flex-col items-start gap-0.5">
                <span>{opt.label}</span>
                {opt.description ? (
                  <span className="text-[10px] font-normal text-muted-foreground">
                    {opt.description}
                  </span>
                ) : null}
              </span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
