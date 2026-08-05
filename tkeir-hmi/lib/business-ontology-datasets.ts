/** Known ``datasets/<id>/business_ontology.yaml`` catalogs for HMI pickers. */

export type BusinessOntologyDatasetOption = {
  id: string;
  label: string;
  description?: string;
};

/** Static catalog aligned with ``configs/collector/topics.yaml`` / datasets/. */
export const BUSINESS_ONTOLOGY_DATASETS: BusinessOntologyDatasetOption[] = [
  {
    id: "osint",
    label: "OSINT",
    description: "Maritime / C2 OSINT business ontology",
  },
  {
    id: "scifact",
    label: "SciFact",
    description: "Scientific claims",
  },
  {
    id: "fiqa",
    label: "FiQA",
    description: "Financial QA",
  },
  {
    id: "arguana",
    label: "ArguAna",
    description: "Argument retrieval",
  },
  {
    id: "scidocs",
    label: "SciDocs",
    description: "Scientific document similarity",
  },
];

export const DEFAULT_BUSINESS_ONTOLOGY_DATASET = "osint";

/** Resolve dataset id from runtime config or fall back to osint. */
export function resolveBusinessOntologyDataset(
  runtimeDefault?: string | null,
  override?: string | null,
): string {
  const fromOverride = override?.trim();
  if (fromOverride) return fromOverride;
  const fromConfig = runtimeDefault?.trim();
  if (fromConfig) return fromConfig;
  return DEFAULT_BUSINESS_ONTOLOGY_DATASET;
}
