"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Moon, Sun } from "lucide-react";

import { AuthButton } from "@/components/auth-button";
import { GlobalIngestPanel } from "@/components/global-ingest-panel";
import { ModeSidebar } from "@/components/mode-sidebar";
import { MyFilesPanel } from "@/components/my-files-panel";
import { ReporterPanel } from "@/components/reporter-panel";
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
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";

const VALID_MODES = new Set<WorkspaceMode>([
  "search",
  "reporter",
  "files",
  "ingest",
]);

const LEGACY_MODE_ALIASES: Record<string, WorkspaceMode> = {
  wiki: "reporter",
  agent: "reporter",
  rag: "search",
};

function parseInitialMode(value?: string | null): WorkspaceMode {
  if (!value) return "search";
  if (LEGACY_MODE_ALIASES[value]) {
    return LEGACY_MODE_ALIASES[value];
  }
  if (VALID_MODES.has(value as WorkspaceMode)) {
    return value as WorkspaceMode;
  }
  return "search";
}

export function RagDashboard({
  initialMode,
}: {
  initialMode?: string | null;
} = {}) {
  const { roles } = useAuth();
  const canIngest =
    roles.includes("c2-admin") || roles.includes("tkeir-admin");
  const [mode, setMode] = useState<WorkspaceMode>(() =>
    parseInitialMode(initialMode),
  );
  // Keep visited panels mounted (hidden) so search/reporter/files/ingest
  // local state survives sidebar mode switches.
  const [visitedModes, setVisitedModes] = useState<Set<WorkspaceMode>>(
    () => new Set([parseInitialMode(initialMode)]),
  );
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null);
  const [agentAvailable, setAgentAvailable] = useState(false);
  const [darkMode, setDarkMode] = useState(true);

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

  useEffect(() => {
    setVisitedModes((prev) => {
      if (prev.has(mode)) return prev;
      const next = new Set(prev);
      next.add(mode);
      return next;
    });
  }, [mode]);

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

  useEffect(() => {
    if (mode === "ingest" && !canIngest) {
      setMode("search");
    }
  }, [mode, canIngest]);

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
          showIngest={canIngest}
        />

        <main className="min-w-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
          {apiHealthy === false &&
            mode !== "reporter" &&
            mode !== "files" &&
            mode !== "ingest" && (
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
            {visitedModes.has("search") && (
              <div
                className={cn(mode !== "search" && "hidden")}
                aria-hidden={mode !== "search"}
                inert={mode !== "search" ? true : undefined}
              >
                <SearchPanel
                  ontology={ontology}
                  ontologyLoading={ontologyLoading}
                  ontologyKey={ontologyKey}
                  activeChunkIds={activeChunkIds}
                  activeLabel={activeLabel}
                  onOntologyUpdate={handleOntologyUpdate}
                  onSelectEntity={handleSelectEntity}
                  onSelectKeyword={handleSelectKeyword}
                  onClearFilter={handleClearFilter}
                />
              </div>
            )}
            {visitedModes.has("reporter") && (
              <div
                className={cn(mode !== "reporter" && "hidden")}
                aria-hidden={mode !== "reporter"}
                inert={mode !== "reporter" ? true : undefined}
              >
                <ReporterPanel agentAvailable={agentAvailable} />
              </div>
            )}
            {visitedModes.has("files") && (
              <div
                className={cn(mode !== "files" && "hidden")}
                aria-hidden={mode !== "files"}
                inert={mode !== "files" ? true : undefined}
              >
                <MyFilesPanel />
              </div>
            )}
            {visitedModes.has("ingest") && canIngest && (
              <div
                className={cn(mode !== "ingest" && "hidden")}
                aria-hidden={mode !== "ingest"}
                inert={mode !== "ingest" ? true : undefined}
              >
                <GlobalIngestPanel />
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
