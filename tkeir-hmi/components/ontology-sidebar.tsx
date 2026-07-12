"use client";

import { Filter, Network, Tag, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MIN_KEYWORD_LENGTH } from "@/lib/constants";
import {
  groupEntitiesByType,
  type FusedOntology,
  type SemanticEntity,
  type SemanticKeyword,
} from "@/lib/types";
import { cn } from "@/lib/utils";

interface OntologySidebarProps {
  ontology: FusedOntology | null;
  activeChunkIds: Set<string> | null;
  activeLabel: string | null;
  onSelectEntity: (entity: SemanticEntity) => void;
  onSelectKeyword: (keyword: SemanticKeyword) => void;
  onClearFilter: () => void;
}

function EntityButton({
  entity,
  selected,
  onClick,
}: {
  entity: SemanticEntity;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-transparent bg-indigo-100 text-indigo-900 hover:bg-indigo-200 dark:bg-indigo-950 dark:text-indigo-100 dark:hover:bg-indigo-900",
      )}
      title={`${entity.chunk_ids.length} linked chunk(s)`}
    >
      {entity.label}
      <span className="opacity-70">({entity.chunk_ids.length})</span>
    </button>
  );
}

function KeywordButton({
  keyword,
  selected,
  onClick,
}: {
  keyword: SemanticKeyword;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
        selected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-transparent bg-emerald-100 text-emerald-900 hover:bg-emerald-200 dark:bg-emerald-950 dark:text-emerald-100 dark:hover:bg-emerald-900",
      )}
      title={`${keyword.chunk_ids.length} linked chunk(s)`}
    >
      {keyword.label}
      <span className="opacity-70">({keyword.chunk_ids.length})</span>
    </button>
  );
}

export function OntologySidebar({
  ontology,
  activeChunkIds,
  activeLabel,
  onSelectEntity,
  onSelectKeyword,
  onClearFilter,
}: OntologySidebarProps) {
  const entityGroups = ontology
    ? groupEntitiesByType(ontology.entities)
    : new Map<string, SemanticEntity[]>();
  const visibleKeywords = ontology
    ? ontology.keywords.filter(
        (keyword) => keyword.label.trim().length >= MIN_KEYWORD_LENGTH,
      )
    : [];

  const hasFilter = activeChunkIds !== null && activeChunkIds.size > 0;

  return (
    <Card className="sticky top-4 h-fit max-h-[calc(100vh-2rem)] overflow-hidden">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Network className="h-5 w-5 text-primary" />
          Ontology Navigator
        </CardTitle>
        {hasFilter && (
          <div className="flex items-center justify-between gap-2 rounded-md bg-muted px-3 py-2 text-xs">
            <span className="flex items-center gap-1 truncate">
              <Filter className="h-3 w-3 shrink-0" />
              <span className="truncate">{activeLabel}</span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2"
              onClick={onClearFilter}
            >
              <X className="h-3 w-3" />
              Clear
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="overflow-y-auto pb-6">
        {!ontology ? (
          <p className="text-sm text-muted-foreground">
            Run a query to load the fused RDF ontology (entities and keywords
            mapped to chunk IDs).
          </p>
        ) : (
          <Tabs defaultValue="entities" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="entities">
                Entities ({ontology.entities.length})
              </TabsTrigger>
              <TabsTrigger value="keywords">
                Keywords ({visibleKeywords.length})
              </TabsTrigger>
            </TabsList>

            <TabsContent value="entities" className="mt-4 space-y-4">
              {ontology.entities.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No named entities in this response.
                </p>
              ) : (
                Array.from(entityGroups.entries()).map(([type, entities]) => (
                  <div key={type} className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="entity">{type}</Badge>
                      <span className="text-xs text-muted-foreground">
                        {entities.length}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {entities.map((entity) => (
                        <EntityButton
                          key={`${entity.type}-${entity.label}`}
                          entity={entity}
                          selected={activeLabel === entity.label}
                          onClick={() => onSelectEntity(entity)}
                        />
                      ))}
                    </div>
                  </div>
                ))
              )}
            </TabsContent>

            <TabsContent value="keywords" className="mt-4 space-y-3">
              {visibleKeywords.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No keywords in this response.
                </p>
              ) : (
                <>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Tag className="h-3 w-3" />
                    Click a keyword to highlight linked chunks
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {visibleKeywords.map((keyword) => (
                      <KeywordButton
                        key={keyword.label}
                        keyword={keyword}
                        selected={activeLabel === keyword.label}
                        onClick={() => onSelectKeyword(keyword)}
                      />
                    ))}
                  </div>
                </>
              )}
            </TabsContent>
          </Tabs>
        )}
      </CardContent>
    </Card>
  );
}
