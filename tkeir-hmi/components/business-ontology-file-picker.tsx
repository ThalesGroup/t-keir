"use client";

import { useRef, useState } from "react";
import { Loader2, Upload, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { parseBusinessOntologyFile } from "@/lib/api";
import { cn } from "@/lib/utils";

export type BusinessOntologyFileValue = {
  payload: Record<string, unknown> | null;
  filename: string | null;
  conceptCount: number;
};

type BusinessOntologyFilePickerProps = {
  value: BusinessOntologyFileValue;
  onChange: (next: BusinessOntologyFileValue) => void;
  disabled?: boolean;
  /** Shown when no file is selected. */
  emptyHint?: string;
  className?: string;
  label?: string;
};

const EMPTY: BusinessOntologyFileValue = {
  payload: null,
  filename: null,
  conceptCount: 0,
};

function countConcepts(payload: Record<string, unknown>): number {
  const concepts = payload.concepts;
  return Array.isArray(concepts) ? concepts.length : 0;
}

/**
 * File picker for ``business_ontology.yaml`` / JSON used at ingest.
 *
 * Parses via the search API and returns the payload for job extras.
 */
export function BusinessOntologyFilePicker({
  value,
  onChange,
  disabled,
  emptyHint = "Optional — otherwise the default dataset ontology is used",
  className,
  label = "Business ontology",
}: BusinessOntologyFilePickerProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      const parsed = await parseBusinessOntologyFile(file);
      const payload = parsed.business_ontology;
      onChange({
        payload,
        filename: parsed.filename || file.name,
        conceptCount: countConcepts(payload),
      });
    } catch (err) {
      onChange(EMPTY);
      setError(
        err instanceof Error
          ? err.message
          : "Failed to parse business ontology file",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed px-3 py-2">
        <label
          className={cn(
            "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-sm",
            (busy || disabled) && "pointer-events-none opacity-50",
          )}
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          {label}
          <input
            ref={inputRef}
            type="file"
            accept=".yaml,.yml,.json,application/json,text/yaml,text/x-yaml"
            className="hidden"
            disabled={busy || disabled}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
              event.currentTarget.value = "";
            }}
          />
        </label>
        {value.filename ? (
          <Badge variant="outline" className="gap-1.5">
            {value.filename}
            <span className="text-muted-foreground">
              ({value.conceptCount} concepts)
            </span>
            <button
              type="button"
              className="rounded p-0.5 hover:bg-muted"
              aria-label="Clear business ontology file"
              disabled={busy || disabled}
              onClick={() => {
                onChange(EMPTY);
                setError(null);
                if (inputRef.current) inputRef.current.value = "";
              }}
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ) : (
          <span className="text-xs text-muted-foreground">{emptyHint}</span>
        )}
      </div>
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : null}
    </div>
  );
}

export const EMPTY_BUSINESS_ONTOLOGY_FILE = EMPTY;
