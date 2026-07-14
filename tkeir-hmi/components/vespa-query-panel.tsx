"use client";

import { memo } from "react";
import { SearchCode } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface VespaQueryPanelProps {
  vespaQuery: string | null;
  loading: boolean;
}

export const VespaQueryPanel = memo(function VespaQueryPanel({
  vespaQuery,
  loading,
}: VespaQueryPanelProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <SearchCode className="h-5 w-5 text-primary" />
            Vespa Search Query
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!vespaQuery?.trim()) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <SearchCode className="h-5 w-5 text-primary" />
          Vespa Search Query
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          JSON payload sent to Vespa hybrid search
        </p>
      </CardHeader>
      <CardContent>
        <Accordion type="single" collapsible defaultValue="vespa">
          <AccordionItem value="vespa" className="border-none">
            <AccordionTrigger className="py-2 text-sm">
              Show full query
            </AccordionTrigger>
            <AccordionContent>
              <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-4 text-xs leading-relaxed">
                {vespaQuery}
              </pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
});
