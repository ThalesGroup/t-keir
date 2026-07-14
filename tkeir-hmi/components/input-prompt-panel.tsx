"use client";

import { memo } from "react";
import { MessageSquareText } from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface InputPromptPanelProps {
  inputPrompt: string | null;
  loading: boolean;
}

export const InputPromptPanel = memo(function InputPromptPanel({
  inputPrompt,
  loading,
}: InputPromptPanelProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageSquareText className="h-5 w-5 text-primary" />
            LLM Input Prompt
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!inputPrompt?.trim()) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquareText className="h-5 w-5 text-primary" />
          LLM Input Prompt
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          System and user messages sent to the language model
        </p>
      </CardHeader>
      <CardContent>
        <Accordion type="single" collapsible defaultValue="prompt">
          <AccordionItem value="prompt" className="border-none">
            <AccordionTrigger className="py-2 text-sm">
              Show full prompt
            </AccordionTrigger>
            <AccordionContent>
              <pre className="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-4 text-xs leading-relaxed">
                {inputPrompt}
              </pre>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  );
});
