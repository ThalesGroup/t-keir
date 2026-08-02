"use client";

import {
  ChevronLeft,
  ChevronRight,
  FolderOpen,
  Newspaper,
  Search,
  Upload,
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

const BASE_MODES: Array<{
  id: WorkspaceMode;
  title: string;
  blurb: string;
  icon: typeof Search;
}> = [
  {
    id: "search",
    title: "Search",
    blurb:
      "Hybrid retrieval with a grounded structured answer, evidence chunks, and ontology navigator.",
    icon: Search,
  },
  {
    id: "reporter",
    title: "Reporter",
    blurb:
      "Retrieve data, generate an editable persona wiki (OKF + ontology), save to My files or send to commander.",
    icon: Newspaper,
  },
  {
    id: "files",
    title: "My files",
    blurb:
      "Import and manage your private documents (indexed to your streaming user space).",
    icon: FolderOpen,
  },
];

const INGEST_MODE = {
  id: "ingest" as const,
  title: "Ingest",
  blurb:
    "Queue global corpus ingest (JSON records → NLP → Vespa). Visible to c2-admin.",
  icon: Upload,
};

interface ModeSidebarProps {
  mode: WorkspaceMode;
  onModeChange: (mode: WorkspaceMode) => void;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
  /** Disable Reporter when agent service is down (phases 2–3 need it). */
  agentAvailable: boolean;
  /** Show Ingest next to Search/RAG/Reporter/My files (admin roles). */
  showIngest?: boolean;
}

export function ModeSidebar({
  mode,
  onModeChange,
  collapsed,
  onCollapsedChange,
  agentAvailable,
  showIngest = false,
}: ModeSidebarProps) {
  const modes = showIngest ? [...BASE_MODES, INGEST_MODE] : BASE_MODES;

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
          {modes.map((item) => {
            const Icon = item.icon;
            const disabled = false;
            return (
              <Button
                key={item.id}
                type="button"
                variant={mode === item.id ? "default" : "ghost"}
                size="icon"
                className="h-10 w-10"
                disabled={disabled}
                title={item.title}
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
            const allowed = new Set(modes.map((m) => m.id));
            if (!allowed.has(value as WorkspaceMode)) {
              return;
            }
            onModeChange(value as WorkspaceMode);
          }}
          className="flex-1 overflow-y-auto px-2 py-1"
        >
          {modes.map((item) => {
            const Icon = item.icon;
            return (
              <AccordionItem
                key={item.id}
                value={item.id}
                className="border-b-0"
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
                  {item.id === "reporter" && !agentAvailable && (
                    <p className="mt-2 text-amber-700 dark:text-amber-400">
                      Wiki/report phases need{" "}
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
