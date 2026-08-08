"use client";

import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  type AgentRunPayload,
  TERMINAL_RUN_STATUSES,
  describeAgentRunActivity,
} from "@/lib/reporter";
import { cn } from "@/lib/utils";

interface AgentRunActivityProps {
  payload: AgentRunPayload | null;
  runId?: string | null;
  className?: string;
  title?: string;
}

export function AgentRunActivity({
  payload,
  runId,
  className,
  title = "Agent activity",
}: AgentRunActivityProps) {
  const activity = describeAgentRunActivity(payload);
  if (!activity && !runId) return null;

  const status = payload?.run?.status || "queued";
  const running = !TERMINAL_RUN_STATUSES.has(status);

  return (
    <div
      className={cn(
        "space-y-3 rounded-md border bg-muted/30 px-3 py-3 text-sm",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {running ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" />
        ) : null}
        <span className="font-medium">{title}</span>
        <Badge variant="outline">{status}</Badge>
        {runId ? (
          <code className="text-xs text-muted-foreground">
            {runId.slice(0, 12)}
          </code>
        ) : null}
        {activity?.agentLabel ? (
          <Badge variant="secondary">{activity.agentLabel}</Badge>
        ) : null}
        {activity?.spiffeId ? (
          <code
            className="max-w-full truncate text-[11px] text-muted-foreground"
            title={activity.spiffeId}
          >
            {activity.spiffeId}
          </code>
        ) : null}
        {typeof activity?.stepCount === "number" && activity.stepCount > 0 ? (
          <span className="text-xs text-muted-foreground">
            {activity.stepCount} step{activity.stepCount === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      {activity ? (
        <>
          <p className="leading-snug">{activity.headline}</p>
          {activity.detail ? (
            <p className="text-xs leading-relaxed text-muted-foreground">
              {activity.detail.length > 280
                ? `${activity.detail.slice(0, 280)}…`
                : activity.detail}
            </p>
          ) : null}

          {activity.handoffs.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                Workflow phases
              </p>
              <ul className="space-y-0.5 text-xs text-muted-foreground">
                {activity.handoffs.map((h, i) => (
                  <li key={`${h.from_agent}-${h.to_agent}-${i}`}>
                    <span className="font-mono text-[11px]">
                      {h.from_agent}
                    </span>
                    {" → "}
                    <span className="font-mono text-[11px]">{h.to_agent}</span>
                    {h.reason ? (
                      <span className="opacity-70">
                        {" "}
                        (
                        {h.reason.replace(/^workflow:[^:]+:/, "phase ")}
                        )
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {activity.recentSteps.length > 0 ? (
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">
                Recent steps
              </p>
              <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-[11px] leading-snug">
                {activity.recentSteps.map((s) => {
                  const actionName = s.tool_call?.name || s.status;
                  return (
                    <li key={s.step_index} className="text-muted-foreground">
                      <span className="text-foreground">[{s.step_index}]</span>{" "}
                      <span className="text-foreground">
                        {activity.agentLabel || "agent"}
                      </span>
                      {" · "}
                      <span className="text-foreground">{actionName}</span>
                      {activity.spiffeId ? (
                        <>
                          {" · "}
                          <span title={activity.spiffeId}>
                            {activity.spiffeId.length > 48
                              ? `${activity.spiffeId.slice(0, 48)}…`
                              : activity.spiffeId}
                          </span>
                        </>
                      ) : null}
                      {s.thought_excerpt
                        ? ` — ${s.thought_excerpt.slice(0, 100)}${
                            s.thought_excerpt.length > 100 ? "…" : ""
                          }`
                        : ""}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : running ? (
            <p className="text-xs text-muted-foreground">
              Waiting for the first reason→act step…
            </p>
          ) : null}

          {activity.usage &&
          (activity.usage.tool_calls ||
            activity.usage.llm_tokens ||
            activity.usage.wall_seconds) ? (
            <p className="text-[11px] text-muted-foreground">
              {[
                typeof activity.usage.tool_calls === "number"
                  ? `${activity.usage.tool_calls} tool calls`
                  : null,
                typeof activity.usage.llm_tokens === "number"
                  ? `${activity.usage.llm_tokens} tokens`
                  : null,
                typeof activity.usage.wall_seconds === "number"
                  ? `${Math.round(activity.usage.wall_seconds)}s`
                  : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
          ) : null}
        </>
      ) : (
        <p className="text-muted-foreground">Starting agent…</p>
      )}
    </div>
  );
}
