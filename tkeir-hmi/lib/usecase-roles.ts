import { readFileSync } from "fs";
import { join } from "path";

import {
  OSINT_FALLBACK,
  parseUsecaseConfig,
  type UsecaseConfig,
} from "./usecase-config";

/** Server-only: read `public/usecase.json` copied by `make hmi-up`. */
export function loadUsecaseConfigFromDisk(): UsecaseConfig {
  try {
    const path = join(process.cwd(), "public", "usecase.json");
    const parsed = parseUsecaseConfig(
      JSON.parse(readFileSync(path, "utf8")),
    );
    if (parsed) return parsed;
  } catch {
    // Pack file not copied yet — OSINT defaults.
  }
  return OSINT_FALLBACK;
}

export function personaPageRoles(): string[] {
  return loadUsecaseConfigFromDisk().pageRoles;
}

export function usecaseAdminRoles(): string[] {
  return loadUsecaseConfigFromDisk().adminRoles;
}
