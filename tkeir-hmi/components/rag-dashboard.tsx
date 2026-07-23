"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Moon, Sun } from "lucide-react";

import { AgentPanel } from "@/components/agent-panel";
import { AuthButton } from "@/components/auth-button";
import { ModeSidebar } from "@/components/mode-sidebar";
import { OntologyNavigator } from "@/components/ontology-navigator";
import { RagPanel } from "@/components/rag-panel";
import { SearchPanel } from "@/components/search-panel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { checkAgentHealth, checkHealth } from "@/lib/api";
import type {
  FusedOntology,
  SemanticEntity,
  SemanticKeyword,
  WorkspaceMode,
} from "@/lib/types";

export function RagDashboard() {
  const [mode, setMode] = useState<WorkspaceMode>("search");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null);
  const [agentAvailable, setAgentAvailable] = useState(false);
  const [darkMode, setDarkMode] = useState(false);

  // Shared across Search + RAG modes
  const [ontology, setOntology] = useState<FusedOntology | null>(null);
  const [ontologyLoading, setOntologyLoading] = useState(false);
  const [ontologyKey, setOntologyKey] = useState("idle");
  const [activeChunkIds, setActiveChunkIds] = useState<Set<string> | null>(
    null,
  );
  const [activeLabel, setActiveLabel] = useState<string | null>(null);

  useEffect(() => {
    void checkHealth().then(setApiHealthy);
    void checkAgentHealth().then(setAgentAvailable);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  const handleOntologyUpdate = useCallback(
    (next: FusedOntology | null, meta?: { loading?: boolean; key?: string }) => {
      if (meta?.loading !== undefined) {
        setOntologyLoading(meta.loading);
      }
      if (meta?.key !== undefined) {
        setOntologyKey(meta.key);
      }
      if (meta?.loading) {
        return;
      }
      setOntology(next);
      setActiveChunkIds(null);
      setActiveLabel(null);
    },
    [],
  );

  const scrollToFirstMatch = useCallback((chunkIds: string[]) => {
    if (chunkIds.length === 0) {
      return;
    }
    const element = document.querySelector(
      `[data-chunk-id="${CSS.escape(chunkIds[0])}"]`,
    );
    element?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const handleSelectEntity = useCallback(
    (entity: SemanticEntity) => {
      if (activeLabel === entity.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      setActiveChunkIds(new Set(entity.chunk_ids));
      setActiveLabel(entity.label);
      scrollToFirstMatch(entity.chunk_ids);
    },
    [activeLabel, scrollToFirstMatch],
  );

  const handleSelectKeyword = useCallback(
    (keyword: SemanticKeyword) => {
      if (activeLabel === keyword.label) {
        setActiveChunkIds(null);
        setActiveLabel(null);
        return;
      }
      setActiveChunkIds(new Set(keyword.chunk_ids));
      setActiveLabel(keyword.label);
      scrollToFirstMatch(keyword.chunk_ids);
    },
    [activeLabel, scrollToFirstMatch],
  );

  const handleClearFilter = useCallback(() => {
    setActiveChunkIds(null);
    setActiveLabel(null);
  }, []);

  const showOntology = mode === "search" || mode === "rag";

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="shrink-0 border-b bg-card/80 backdrop-blur">
        <div className="flex items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              T-KEIR
            </p>
            <h1 className="text-lg font-bold tracking-tight sm:text-xl">
              Corpus workspace
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <a
              href="/agents"
              className="hidden text-sm text-muted-foreground underline-offset-2 hover:underline sm:inline"
            >
              Agents
            </a>
            <a
              href="/admin"
              className="hidden text-sm text-muted-foreground underline-offset-2 hover:underline sm:inline"
            >
              Admin
            </a>
            <AuthButton />
            <Button
              variant="outline"
              size="icon"
              onClick={() => setDarkMode((value) => !value)}
              aria-label="Toggle dark mode"
            >
              {darkMode ? <Sun /> : <Moon />}
            </Button>
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <ModeSidebar
          mode={mode}
          onModeChange={setMode}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
          agentAvailable={agentAvailable}
        />

        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          {apiHealthy === false && mode !== "agent" && (
            <Alert variant="destructive" className="mb-6">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>RAG API unreachable</AlertTitle>
              <AlertDescription>
                Start the FastAPI server with{" "}
                <code className="rounded bg-muted px-1 py-0.5 text-xs">
                  make rag
                </code>{" "}
                (default port 8090).
              </AlertDescription>
            </Alert>
          )}

          <div className="space-y-6">
            {mode === "search" && (
              <SearchPanel
                onOntologyUpdate={handleOntologyUpdate}
                activeChunkIds={activeChunkIds}
              />
            )}
            {mode === "rag" && (
              <RagPanel
                onOntologyUpdate={handleOntologyUpdate}
                activeChunkIds={activeChunkIds}
              />
            )}
            {mode === "agent" && <AgentPanel available={agentAvailable} />}

            {showOntology && (
              <div className="mx-auto w-full max-w-5xl">
                <OntologyNavigator
                  ontology={ontology}
                  loading={ontologyLoading}
                  activeChunkIds={activeChunkIds}
                  activeLabel={activeLabel}
                  onSelectEntity={handleSelectEntity}
                  onSelectKeyword={handleSelectKeyword}
                  onClearFilter={handleClearFilter}
                  accordionKey={ontologyKey}
                />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
