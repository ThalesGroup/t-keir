/** Persona → agent workflow + OKF wiki prompt presets (Reporter / Agents). */

import {
  getUsecaseConfig,
  type PersonaWorkflowPreset,
} from "@/lib/usecase-config";

export type { PersonaWorkflowPreset };

export type OsintPersonaId =
  | "analyst"
  | "moc-watch"
  | "humint"
  | "commander"
  | "admin";

export type EnterprisePersonaId =
  | "ceo"
  | "cfo"
  | "cto"
  | "ciso"
  | "cdo";

export type PersonaId = OsintPersonaId | EnterprisePersonaId | string;

export function hmiUsecase(): string {
  return (
    process.env.NEXT_PUBLIC_TKEIR_USECASE?.trim().toLowerCase() || "osint"
  );
}

const ENTERPRISE_PRESETS: PersonaWorkflowPreset[] = [
  {
    role: "ent-ceo",
    personaId: "ceo",
    label: "CEO",
    reportForm: "board_sitrep",
    goal: "Board SITREP: material risks and KRIs this period.",
    topic: "Executive situation",
    workflow: "persona_ceo",
    wikiPrompt: "ceo_prompt",
    answerTemplate: "ent_board_sitrep",
  },
  {
    role: "ent-cfo",
    personaId: "cfo",
    label: "CFO",
    reportForm: "decision_brief",
    goal: "Decision brief: capital exposure and outstanding decisions.",
    topic: "Financial risk",
    workflow: "persona_cfo",
    wikiPrompt: "cfo_prompt",
    answerTemplate: "ent_decision_brief",
  },
  {
    role: "ent-cto",
    personaId: "cto",
    label: "CTO",
    reportForm: "risk_summary",
    goal: "Risk summary: what the indexed corpus contains.",
    topic: "Corpus coverage",
    workflow: "persona_cto",
    wikiPrompt: "cto_prompt",
    answerTemplate: "ent_risk_summary",
  },
  {
    role: "ent-ciso",
    personaId: "ciso",
    label: "CISO",
    reportForm: "field_report",
    goal: "Field report: source access and security posture.",
    topic: "Source security",
    workflow: "persona_ciso",
    wikiPrompt: "ciso_prompt",
    answerTemplate: "ent_field_report",
  },
  {
    role: "ent-cdo",
    personaId: "cdo",
    label: "CDO",
    reportForm: "risk_summary",
    goal: "Data risk summary: quality gaps and recommendations.",
    topic: "Data risk",
    workflow: "persona_cdo",
    wikiPrompt: "cdo_prompt",
    answerTemplate: "ent_risk_summary",
  },
];

function presetsForResolve(): PersonaWorkflowPreset[] {
  const cfg = getUsecaseConfig();
  if (
    hmiUsecase() === "enterprise" &&
    !cfg.workflowPresets.some((p) => p.role.startsWith("ent-"))
  ) {
    return ENTERPRISE_PRESETS;
  }
  return cfg.workflowPresets;
}

export function resolvePersonaWorkflowPreset(options: {
  roles: string[];
  activePersonaId?: string | null;
}): PersonaWorkflowPreset {
  const { roles, activePersonaId } = options;
  const presets = presetsForResolve();
  const byPersona = Object.fromEntries(
    presets.map((p) => [p.personaId, p]),
  ) as Record<string, PersonaWorkflowPreset>;
  if (activePersonaId && byPersona[activePersonaId]) {
    return byPersona[activePersonaId];
  }
  for (const preset of presets) {
    if (roles.includes(preset.role)) {
      return preset;
    }
  }
  if (roles.includes("tkeir-admin")) {
    const adminPreset = presets.find((p) => p.personaId === "admin");
    if (adminPreset) return adminPreset;
  }
  return presets[0] ?? ENTERPRISE_PRESETS[0];
}

export const LLM_WIKI_WORKFLOW = "llm_wiki";
/** Search → wiki_upsert → answer_generate (compose template). */
export const RAG_WITH_WIKI_WORKFLOW = "rag_with_wiki";
/** Fallback generic OKF wiki prompt (no persona checklist). */
export const OKF_WIKI_PROMPT = "okf_wiki_prompt";

export function orderWorkflowNames(
  names: string[],
  preferred: string,
): string[] {
  const unique = [...new Set(names)];
  const persona = unique
    .filter((n) => n.startsWith("persona_"))
    .sort((a, b) => a.localeCompare(b));
  const rest = unique
    .filter((n) => !n.startsWith("persona_"))
    .sort((a, b) => a.localeCompare(b));
  const ordered = [...persona, ...rest];
  const prefer =
    preferred && ordered.includes(preferred)
      ? preferred
      : ordered.includes(RAG_WITH_WIKI_WORKFLOW)
        ? RAG_WITH_WIKI_WORKFLOW
        : preferred;
  if (prefer && ordered.includes(prefer)) {
    return [prefer, ...ordered.filter((n) => n !== prefer)];
  }
  return ordered;
}
