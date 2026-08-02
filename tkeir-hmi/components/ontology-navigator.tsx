"use client";

import { Network } from "lucide-react";
import { memo } from "react";

import { OntologySidebar } from "@/components/ontology-sidebar";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type {
  FusedOntology,
  SemanticEntity,
  SemanticKeyword,
} from "@/lib/types";

export type OntologyUpdateHandler = (
  ontology: FusedOntology | null,
  meta?: { loading?: boolean; key?: string },
) => void;

export interface OntologyNavigatorProps {
  ontology: FusedOntology | null;
  loading?: boolean;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
  /** Accordion remount key (e.g. last query) so default open state refreshes. */
  accordionKey?: string;
}

/**
 * Shared ontology accordion used by both Search and RAG workspace modes.
 */
export const OntologyNavigator = memo(function OntologyNavigator({
  ontology,
  loading = false,
  activeChunkIds,
  activeLabel,
  onSelectEntity,
  onSelectKeyword,
  onClearFilter,
  accordionKey = "ontology",
}: OntologyNavigatorProps) {
  // Always open by default so a late ontology load (key remount while null)
  // does not leave the navigator collapsed/empty-looking.
  return (
    <Accordion
      key={accordionKey}
      type="multiple"
      defaultValue={["ontology"]}
      className="rounded-xl border bg-card px-4 shadow-sm"
    >
      <AccordionItem value="ontology" className="border-b-0">
        <AccordionTrigger className="text-sm font-medium hover:no-underline">
          <span className="flex items-center gap-2">
            <Network className="h-4 w-4 text-primary" />
            Ontology navigator
            {ontology ? ` (${ontology.entities.length} entities)` : ""}
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <OntologySidebar
            embedded
            ontology={ontology}
            loading={loading}
            activeChunkIds={activeChunkIds}
            activeLabel={activeLabel}
            onSelectEntity={onSelectEntity}
            onSelectKeyword={onSelectKeyword}
            onClearFilter={onClearFilter}
          />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
});
