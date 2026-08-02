export type RuntimeConfig = {
  keycloakUrl: string;
  realm: string;
  clientId: string;
  ragBaseUrl: string;
  /** Server-side ingest dump path for analyzed_document.json (RAG ontology). */
  analyzedDocumentsPath: string;
  /** datasets/<name>/business_ontology.yaml loaded on each search/RAG query. */
  businessOntologyDataset: string;
};

function isNonEmptyString(x: unknown): x is string {
  return typeof x === "string" && x.trim().length > 0;
}

function validateRuntimeConfig(payload: any): RuntimeConfig {
  const cfg = payload ?? {};
  const keycloakUrl = cfg.keycloakUrl;
  const realm = cfg.realm;
  const clientId = cfg.clientId;
  const ragBaseUrl = cfg.ragBaseUrl;
  const analyzedDocumentsPath =
    cfg.analyzedDocumentsPath ?? "workspace/ingest";
  const businessOntologyDataset = cfg.businessOntologyDataset ?? "osint";

  if (
    !isNonEmptyString(keycloakUrl) ||
    !isNonEmptyString(realm) ||
    !isNonEmptyString(clientId) ||
    !isNonEmptyString(ragBaseUrl) ||
    !isNonEmptyString(analyzedDocumentsPath) ||
    !isNonEmptyString(businessOntologyDataset)
  ) {
    throw new Error(
      "Invalid config.json (expected keycloakUrl, realm, clientId, ragBaseUrl, analyzedDocumentsPath, businessOntologyDataset as non-empty strings)",
    );
  }

  return {
    keycloakUrl,
    realm,
    clientId,
    ragBaseUrl,
    analyzedDocumentsPath,
    businessOntologyDataset,
  };
}

/**
 * Loads `/config.json` at runtime (client-side).
 * This enables deploying the same build into different classified enclaves.
 */
export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  const res = await fetch("/config.json", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(
      `Failed to load /config.json (${res.status} ${res.statusText})`,
    );
  }

  const payload = (await res.json()) as any;
  return validateRuntimeConfig(payload);
}

