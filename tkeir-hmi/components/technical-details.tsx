"use client";

import { memo } from "react";
import { Wrench } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface TechnicalDetailsProps {
  inputPrompt: string | null;
  vespaQuery: string | null;
  loading?: boolean;
}

/**
 * Bottom groupbox for technical RAG diagnostics (prompt + Vespa query).
 * Collapsed by default so the main answer / evidence stay primary.
 */
export const TechnicalDetails = memo(function TechnicalDetails({
  inputPrompt,
  vespaQuery,
  loading = false,
}: TechnicalDetailsProps) {
  const hasPrompt = Boolean(inputPrompt?.trim());
  const hasQuery = Boolean(vespaQuery?.trim());

  if (loading) {
    return (
      <Card className="border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
            <Wrench className="h-4 w-4" />
            Technical details
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!hasPrompt && !hasQuery) {
    return null;
  }

  return (
    <Card className="border-dashed">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Wrench className="h-4 w-4" />
          Technical details
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          LLM prompts and Vespa search payload (diagnostics)
        </p>
      </CardHeader>
      <CardContent>
        <Accordion type="multiple" className="w-full">
          {hasPrompt && (
            <AccordionItem value="prompt">
              <AccordionTrigger className="text-sm">
                LLM input prompt
              </AccordionTrigger>
              <AccordionContent>
                <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed">
                  {inputPrompt}
                </pre>
              </AccordionContent>
            </AccordionItem>
          )}
          {hasQuery && (
            <AccordionItem value="vespa">
              <AccordionTrigger className="text-sm">
                Vespa search query
              </AccordionTrigger>
              <AccordionContent>
                <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-[11px] leading-relaxed">
                  {vespaQuery}
                </pre>
              </AccordionContent>
            </AccordionItem>
          )}
        </Accordion>
      </CardContent>
    </Card>
  );
});
