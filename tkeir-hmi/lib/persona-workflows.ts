/** Persona → agent workflow + OKF wiki prompt presets (Reporter / Agents). */

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

export type PersonaId = OsintPersonaId | EnterprisePersonaId;

export type PersonaWorkflowPreset = {
  role: string;
  personaId: PersonaId;
  label: string;
  reportForm: string;
  goal: string;
  topic: string;
  /** Phase-3 persona report workflow */
  workflow: string;
  /**
   * Persona OKF wiki prompt agent (`*_prompt.yaml`). HMI sends this as
   * `params.prompt_name` / `wiki_agent` for `llm_wiki` / `rag_with_wiki`
   * so structured facts come from agent config — not hardcoded in OKF.
   */
  wikiPrompt: string;
  /** Compose answer template for `rag_with_wiki` / `answer_generate`. */
  answerTemplate: string;
};

export const PERSONA_WORKFLOW_PRESETS: PersonaWorkflowPreset[] = [
  {
    role: "c2-j2-analyst",
    personaId: "analyst",
    label: "J2 Analyst",
    reportForm: "intsum",
    goal: "Tell me everything the system knows about MT RED SEA EAGLE.",
    topic: "MT RED SEA EAGLE",
    workflow: "persona_j2_analyst",
    wikiPrompt: "j2_analyst_prompt",
    answerTemplate: "otan_intsum",
  },
  {
    role: "c2-moc-watch",
    personaId: "moc-watch",
    label: "MOC Watch",
    reportForm: "sitrep",
    goal: "Summarise the Gulf of Aden situation for the 08:00 SITREP.",
    topic: "Gulf of Aden / Bab-el-Mandeb",
    workflow: "persona_moc_watch",
    wikiPrompt: "moc_watch_prompt",
    answerTemplate: "otan_sitrep",
  },
  {
    role: "c2-j2x-humint",
    personaId: "humint",
    label: "J2X HUMINT",
    reportForm: "spotrep",
    goal: "Which sources can I task on Fujairah OPL to cover PIR-02?",
    topic: "PIR-02 / Fujairah OPL",
    workflow: "persona_j2x_humint",
    wikiPrompt: "j2x_humint_prompt",
    answerTemplate: "otan_spotrep",
  },
  {
    role: "c2-ctf-commander",
    personaId: "commander",
    label: "CTF Commander",
    reportForm: "commander_brief",
    goal: "Brief me — RED SEA EAGLE situation, decisions outstanding.",
    topic: "MT RED SEA EAGLE",
    workflow: "persona_ctf_commander",
    wikiPrompt: "ctf_commander_prompt",
    answerTemplate: "otan_commander_brief",
  },
  {
    role: "c2-admin",
    personaId: "admin",
    label: "Admin",
    reportForm: "intsum",
    goal: "Report what the shared corpus knows about MT RED SEA EAGLE.",
    topic: "MT RED SEA EAGLE",
    workflow: "persona_admin",
    wikiPrompt: "admin_prompt",
    answerTemplate: "otan_intsum",
  },
  // Enterprise (available when usecase packs + Keycloak roles are present).
  {
    role: "ent-ceo",
    personaId: "ceo",
    label: "CEO",
    reportForm: "board_sitrep",
    goal: "Board SITREP: material risks and KRIs this period.",
    topic: "Executive situation",
    workflow: "persona_ceo",
    wikiPrompt: "ceo_prompt",
    answerTemplate: "board_sitrep",
  },
  {
    role: "ent-cfo",
    personaId: "cfo",
    label: "CFO",
    reportForm: "risk_summary",
    goal: "Risk summary for financial exposures in scope.",
    topic: "Financial risk",
    workflow: "persona_cfo",
    wikiPrompt: "cfo_prompt",
    answerTemplate: "risk_summary",
  },
  {
    role: "ent-cto",
    personaId: "cto",
    label: "CTO",
    reportForm: "decision_brief",
    goal: "Decision brief: platform risks and decisions required.",
    topic: "Platform decisions",
    workflow: "persona_cto",
    wikiPrompt: "cto_prompt",
    answerTemplate: "decision_brief",
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
    answerTemplate: "field_report",
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
    answerTemplate: "risk_summary",
  },
];

const BY_ROLE = Object.fromEntries(
  PERSONA_WORKFLOW_PRESETS.map((p) => [p.role, p]),
) as Record<string, PersonaWorkflowPreset>;

const BY_PERSONA = Object.fromEntries(
  PERSONA_WORKFLOW_PRESETS.map((p) => [p.personaId, p]),
) as Record<string, PersonaWorkflowPreset>;

export function resolvePersonaWorkflowPreset(options: {
  roles: string[];
  activePersonaId?: string | null;
}): PersonaWorkflowPreset {
  const { roles, activePersonaId } = options;
  if (activePersonaId && BY_PERSONA[activePersonaId]) {
    return BY_PERSONA[activePersonaId];
  }
  for (const preset of PERSONA_WORKFLOW_PRESETS) {
    if (roles.includes(preset.role)) {
      return preset;
    }
  }
  if (roles.includes("tkeir-admin") && BY_ROLE["c2-admin"]) {
    return BY_ROLE["c2-admin"];
  }
  return BY_ROLE["c2-j2-analyst"];
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
