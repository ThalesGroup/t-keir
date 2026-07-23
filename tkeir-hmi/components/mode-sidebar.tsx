"use client";

import {
  Bot,
  ChevronLeft,
  ChevronRight,
  FileText,
  Search,
} from "lucide-react";

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import type { WorkspaceMode } from "@/lib/types";
import { cn } from "@/lib/utils";

const MODES: Array<{
  id: WorkspaceMode;
  title: string;
  blurb: string;
  icon: typeof Search;
}> = [
  {
    id: "search",
    title: "Search",
    blurb: "Simple retrieval — documents and chunks, Google-style results.",
    icon: Search,
  },
  {
    id: "rag",
    title: "RAG",
    blurb: "Ask a question and generate a grounded markdown report.",
    icon: FileText,
  },
  {
    id: "agent",
    title: "Agent",
    blurb:
      "Dialog with researcher / workflows to explore data and compose a custom report.",
    icon: Bot,
  },
];

interface ModeSidebarProps {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  agentAvailable: boolean;
}

export function ModeSidebar({
  mode,
  onModeChange,
  collapsed,
  onCollapsedChange,
  agentAvailable,
}: ModeSidebarProps) {
  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r bg-card/90 transition-[width] duration-200",
        collapsed ? "w-14" : "w-72",
      )}
    >
      <div
        className={cn(
          "flex items-center border-b px-2 py-3",
          collapsed ? "justify-center" : "justify-between gap-2 px-3",
        )}
      >
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-primary">
              Workspace
            </p>
            <p className="truncate text-sm font-medium">Choose a mode</p>
          </div>
        )}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 shrink-0"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => onCollapsedChange(!collapsed)}
        >
          {collapsed ? <ChevronRight /> : <ChevronLeft />}
        </Button>
      </div>

      {collapsed ? (
        <nav className="flex flex-col items-center gap-1 p-2" aria-label="Modes">
          {MODES.map((item) => {
            const Icon = item.icon;
            const disabled = item.id === "agent" && !agentAvailable;
            return (
              <Button
                key={item.id}
                type="button"
                variant={mode === item.id ? "default" : "ghost"}
                size="icon"
                className="h-10 w-10"
                disabled={disabled}
                title={
                  disabled
                    ? "Agent service unavailable (make agent)"
                    : item.title
                }
                aria-label={item.title}
                aria-current={mode === item.id ? "page" : undefined}
                onClick={() => onModeChange(item.id)}
              >
                <Icon />
              </Button>
            );
          })}
        </nav>
      ) : (
        <Accordion
          type="single"
          collapsible
          value={mode}
          onValueChange={(value) => {
            if (value === "search" || value === "rag" || value === "agent") {
              if (value === "agent" && !agentAvailable) {
                return;
              }
              onModeChange(value);
            }
          }}
          className="flex-1 overflow-y-auto px-2 py-1"
        >
          {MODES.map((item) => {
            const Icon = item.icon;
            const disabled = item.id === "agent" && !agentAvailable;
            return (
              <AccordionItem
                key={item.id}
                value={item.id}
                disabled={disabled}
                className={cn(
                  "border-b-0",
                  disabled && "opacity-50",
                )}
              >
                <AccordionTrigger
                  className={cn(
                    "rounded-md px-2 py-3 hover:no-underline",
                    mode === item.id && "bg-primary/10 text-primary",
                  )}
                >
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <Icon className="h-4 w-4 shrink-0" />
                    {item.title}
                  </span>
                </AccordionTrigger>
                <AccordionContent className="px-2 pb-3 text-xs leading-relaxed text-muted-foreground">
                  {item.blurb}
                  {disabled && (
                    <p className="mt-2 text-destructive">
                      Start the agent service with{" "}
                      <code className="rounded bg-muted px-1">make agent</code>.
                    </p>
                  )}
                </AccordionContent>
              </AccordionItem>
            );
          })}
        </Accordion>
      )}
    </aside>
  );
}
