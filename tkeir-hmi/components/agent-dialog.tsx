"use client";

import { Bot, Loader2, Send, User } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resolvePersonaWorkflowPreset } from "@/lib/persona-workflows";
import { cn } from "@/lib/utils";
import { useAuth } from "@/src/auth/AuthProvider";
import { apiFetch } from "@/src/auth/useApiClient";

type ChatRole = "user" | "assistant" | "system";

type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  runId?: string;
};

type RunPayload = {
  run?: {
    run_id?: string;
    status?: string;
    error?: string | null;
    result?: {
      findings?: Array<{ claim: string; chunk_ids?: string[] }>;
      unfilled?: string[];
      notes?: string;
    } | null;
  };
  handoffs?: Array<{ from_agent: string; to_agent: string; reason: string }>;
  compose_result?: {
    markdown?: string;
    unfilled?: string[];
  } | null;
};

type Mode = "researcher" | "persona";

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function formatRunReply(payload: RunPayload): string {
  const lines: string[] = [];
  const status = payload.run?.status ?? "unknown";
  if (payload.run?.error) {
    lines.push(`Status: ${status}`);
    lines.push(`Error: ${payload.run.error}`);
    return lines.join("\n");
  }

  const findings = payload.run?.result?.findings ?? [];
  if (findings.length) {
    lines.push("Grounded findings:");
    for (const finding of findings) {
      const cites = (finding.chunk_ids ?? []).slice(0, 4).join(", ");
      lines.push(
        `• ${finding.claim}${cites ? ` [${cites}]` : ""}`,
      );
    }
  }

  if (payload.handoffs?.length) {
    lines.push("");
    lines.push(
      `Handoffs: ${payload.handoffs
        .map((h) => `${h.from_agent}→${h.to_agent}`)
        .join(", ")}`,
    );
  }

  if (payload.compose_result?.markdown?.trim()) {
    lines.push("");
    lines.push("Compose preview:");
    lines.push(payload.compose_result.markdown.trim());
  }

  const unfilled = [
    ...(payload.run?.result?.unfilled ?? []),
    ...(payload.compose_result?.unfilled ?? []),
  ];
  if (unfilled.length) {
    lines.push("");
    lines.push(`Unfilled: ${unfilled.join("; ")}`);
  }

  if (!lines.length) {
    return `Run finished (${status}) with no grounded findings yet.`;
  }
  return lines.join("\n");
}

interface AgentDialogProps {
  initialGoal?: string;
  className?: string;
}

/**
 * Chat-style dialog to ask the corpus via tkeir-agent (researcher or persona workflow).
 */
export function AgentDialog({
  initialGoal = "",
  className,
}: AgentDialogProps) {
  const { roles, activePersonaId } = useAuth();
  const preset = useMemo(
    () => resolvePersonaWorkflowPreset({ roles, activePersonaId }),
    [roles, activePersonaId],
  );
  const [mode, setMode] = useState<Mode>("persona");
  const [draft, setDraft] = useState(initialGoal || preset.goal);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!draft.trim()) {
      setDraft(preset.goal);
    }
  }, [preset.goal, draft]);

  useEffect(() => {
    if (initialGoal.trim() && !draft.trim()) {
      setDraft(initialGoal);
    }
  }, [initialGoal, draft]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const pollUntilDone = useCallback(async (runId: string): Promise<RunPayload> => {
    const maxAttempts = 120;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const res = await apiFetch(
        `/api/agent/agent/runs/${encodeURIComponent(runId)}`,
        { cache: "no-store" },
      );
      if (!res.ok) {
        throw new Error(`Poll failed (${res.status})`);
      }
      const payload = (await res.json()) as RunPayload;
      const status = payload.run?.status ?? "";
      if (
        status === "succeeded" ||
        status === "failed" ||
        status === "blocked" ||
        status === "killed" ||
        status === "cancelled"
      ) {
        return payload;
      }
      await new Promise((resolve) => {
        window.setTimeout(resolve, 2000);
      });
    }
    throw new Error("Timed out waiting for the agent run");
  }, []);

  async function sendMessage() {
    const goal = draft.trim();
    if (!goal || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    const userMsg: ChatMessage = { id: newId(), role: "user", text: goal };
    setMessages((prev) => [...prev, userMsg]);
    setDraft("");

    try {
      const body =
        mode === "researcher"
          ? { agent: "researcher", goal }
          : {
              workflow: preset.workflow,
              goal,
              params: {
                topic: preset.topic || goal,
                report_form: preset.reportForm,
                query: goal,
              },
            };
      const res = await apiFetch("/api/agent/agent/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const created = (await res.json()) as {
        run_id?: string;
        detail?: string;
      };
      if (!res.ok || !created.run_id) {
        throw new Error(created.detail || `Start failed (${res.status})`);
      }

      const modeLabel =
        mode === "researcher" ? "researcher" : preset.workflow;
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "system",
          text: `Run ${created.run_id} started (${modeLabel})…`,
          runId: created.run_id,
        },
      ]);

      const payload = await pollUntilDone(created.run_id);
      setMessages((prev) => [
        ...prev,
        {
          id: newId(),
          role: "assistant",
          text: formatRunReply(payload),
          runId: created.run_id,
        },
      ]);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Agent request failed";
      setError(message);
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "system", text: message },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <p className="text-xs text-muted-foreground">
        Ask grounded questions via tkeir-agent. Default workflow:{" "}
        <code className="rounded bg-muted px-1 py-0.5">{preset.workflow}</code>{" "}
        ({preset.label} / {preset.reportForm}). Claims without chunk citations
        are dropped.
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant={mode === "persona" ? "default" : "outline"}
          className="h-7"
          disabled={busy}
          onClick={() => setMode("persona")}
        >
          Workflow ({preset.workflow})
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === "researcher" ? "default" : "outline"}
          className="h-7"
          disabled={busy}
          onClick={() => setMode("researcher")}
        >
          Researcher
        </Button>
      </div>

      <div className="flex max-h-[min(28rem,60vh)] flex-col gap-2 overflow-y-auto rounded-md border bg-muted/20 p-3">
        {messages.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No messages yet. Try the persona goal or your last search query.
          </p>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={cn(
                "flex gap-2 text-sm",
                message.role === "user" ? "justify-end" : "justify-start",
              )}
            >
              {message.role !== "user" && (
                <Bot className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              )}
              <div
                className={cn(
                  "max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 text-xs leading-relaxed",
                  message.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : message.role === "system"
                      ? "bg-muted text-muted-foreground"
                      : "border bg-card",
                )}
              >
                {message.text}
              </div>
              {message.role === "user" && (
                <User className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              )}
            </div>
          ))
        )}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Agent working…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void sendMessage();
        }}
      >
        <Input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={`Ask via ${preset.workflow}…`}
          disabled={busy}
          className="text-sm"
        />
        <Button type="submit" size="icon" disabled={busy || !draft.trim()}>
          <Send className="h-4 w-4" />
          <span className="sr-only">Send</span>
        </Button>
      </form>
    </div>
  );
}
