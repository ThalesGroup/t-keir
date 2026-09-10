/** Shared usecase HMI types and OSINT fallback (no Node `fs` — safe for client). */

export type PersonaDef = {
  id: string;
  label: string;
  roles: string[];
};

export type PersonaWorkflowPreset = {
  role: string;
  personaId: string;
  label: string;
  reportForm: string;
  goal: string;
  topic: string;
  workflow: string;
  wikiPrompt: string;
  answerTemplate: string;
};

export type DemoAccount = {
  user: string;
  password: string;
  clearance: string;
  role?: string;
};

export type UsecaseConfig = {
  personas: PersonaDef[];
  workflowPresets: PersonaWorkflowPreset[];
  pageRoles: string[];
  adminRoles: string[];
  ingestRoles: string[];
  shareRoles: string[];
  demoAccounts: DemoAccount[];
};

export const OSINT_FALLBACK: UsecaseConfig = {
  personas: [
    { id: "analyst", label: "Analyst", roles: ["c2-j2-analyst"] },
    { id: "moc-watch", label: "MOC Watch", roles: ["c2-moc-watch"] },
    { id: "humint", label: "HUMINT", roles: ["c2-j2x-humint"] },
    { id: "commander", label: "Commander", roles: ["c2-ctf-commander"] },
    { id: "admin", label: "Admin", roles: ["c2-admin", "tkeir-admin"] },
  ],
  workflowPresets: [
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
  ],
  pageRoles: [
    "c2-j2-analyst",
    "c2-moc-watch",
    "c2-j2x-humint",
    "c2-ctf-commander",
    "c2-admin",
    "tkeir-admin",
  ],
  adminRoles: ["c2-admin", "tkeir-admin"],
  ingestRoles: ["c2-admin", "tkeir-admin"],
  shareRoles: ["c2-j2-analyst", "c2-moc-watch", "c2-j2x-humint"],
  demoAccounts: [
    { user: "analyst", password: "analyst", clearance: "SECRET", role: "J2 Analyst" },
    { user: "moc-watch", password: "moc-watch", clearance: "FOUO", role: "MOC Watch" },
    { user: "humint", password: "humint", clearance: "SECRET", role: "HUMINT" },
    { user: "commander", password: "commander", clearance: "SECRET", role: "CTF Commander" },
    { user: "c2-admin", password: "c2-admin", clearance: "SECRET", role: "Admin" },
  ],
};

let cached: UsecaseConfig | null = null;

function isNonEmptyStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function parseUsecaseConfig(payload: unknown): UsecaseConfig | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = payload as Partial<UsecaseConfig>;
  if (!Array.isArray(raw.personas) || !Array.isArray(raw.workflowPresets)) {
    return null;
  }
  return {
    personas: raw.personas as PersonaDef[],
    workflowPresets: raw.workflowPresets as PersonaWorkflowPreset[],
    pageRoles: isNonEmptyStringArray(raw.pageRoles)
      ? raw.pageRoles
      : OSINT_FALLBACK.pageRoles,
    adminRoles: isNonEmptyStringArray(raw.adminRoles)
      ? raw.adminRoles
      : OSINT_FALLBACK.adminRoles,
    ingestRoles: isNonEmptyStringArray(raw.ingestRoles)
      ? raw.ingestRoles
      : OSINT_FALLBACK.ingestRoles,
    shareRoles: isNonEmptyStringArray(raw.shareRoles)
      ? raw.shareRoles
      : OSINT_FALLBACK.shareRoles,
    demoAccounts: Array.isArray(raw.demoAccounts)
      ? (raw.demoAccounts as DemoAccount[])
      : OSINT_FALLBACK.demoAccounts,
  };
}

export function setUsecaseConfig(config: UsecaseConfig): void {
  cached = config;
}

export function getUsecaseConfig(): UsecaseConfig {
  return cached ?? OSINT_FALLBACK;
}

export async function loadUsecaseConfig(): Promise<UsecaseConfig> {
  if (cached) return cached;
  try {
    const res = await fetch("/usecase.json", { cache: "no-store" });
    if (res.ok) {
      const parsed = parseUsecaseConfig(await res.json());
      if (parsed) {
        cached = parsed;
        return parsed;
      }
    }
  } catch {
    // Fall back to shipped OSINT defaults.
  }
  cached = OSINT_FALLBACK;
  return cached;
}

export function hasAnyRole(roles: string[], allowed: string[]): boolean {
  return allowed.some((role) => roles.includes(role));
}
