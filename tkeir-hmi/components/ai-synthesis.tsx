"use client";

import { memo } from "react";
import { AlertCircle, Bot, Sparkles } from "lucide-react";

import { MarkdownContent } from "@/components/markdown-content";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface AiSynthesisProps {
  answer: string | null;
  loading: boolean;
  vespaHits?: number;
  answerUnavailable?: boolean;
}

export const AiSynthesis = memo(function AiSynthesis({
  answer,
  loading,
  vespaHits,
  answerUnavailable = false,
}: AiSynthesisProps) {
  if (loading) {
    return (
      <Card className="border-primary/20 bg-gradient-to-br from-primary/5 to-transparent">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-5 w-5 text-primary" />
            AI Synthesis — Short Answer
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    );
  }

  if (!answer) {
    return (
      <Card className="border-dashed">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base text-muted-foreground">
            <Bot className="h-5 w-5" />
            AI Synthesis — Short Answer
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Submit a question to generate a grounded answer from retrieved
            chunks and the fused ontology.
          </p>
        </CardContent>
      </Card>
    );
  }

  const unavailable = answerUnavailable;

  if (unavailable) {
    return (
      <Alert variant="warning">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Information unavailable</AlertTitle>
        <AlertDescription className="text-warning-foreground/90">
          {answer}
          {typeof vespaHits === "number" && (
            <span className="mt-2 block text-xs opacity-80">
              Vespa returned {vespaHits} raw hit(s). Try broadening the query
              or increasing max hits.
            </span>
          )}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Card className="border-primary/30 bg-gradient-to-br from-primary/10 via-card to-card shadow-md">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-5 w-5 text-primary" />
          AI Synthesis
        </CardTitle>
      </CardHeader>
      <CardContent>
        <MarkdownContent content={answer} className="text-base [&_p]:text-base" />
        {typeof vespaHits === "number" && (
          <p className="mt-3 text-xs text-muted-foreground">
            Grounded on {vespaHits} Vespa hit(s)
          </p>
        )}
      </CardContent>
    </Card>
  );
});
