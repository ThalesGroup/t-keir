/** Coverage between an external business ontology and fused / chunk surfaces. */

import type { FusedOntology, SearchChunkHit } from "@/lib/types";

export type BoConceptSurface = {
  conceptId: string;
  preferredLabel: string;
  /** Normalized labels used for matching (preferred, synonyms, surfaces, id). */
  surfaces: string[];
};

export type OntologyCoverage = {
  total: number;
  matched: number;
  /** 0–1 */
  ratio: number;
  matchedConcepts: BoConceptSurface[];
  missingConcepts: BoConceptSurface[];
};

function normalize(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[_/]+/g, " ")
    .replace(/\s+/g, " ");
}

function asConceptRows(payload: unknown): Record<string, unknown>[] {
  if (!payload) return [];
  if (Array.isArray(payload)) {
    return payload.filter(
      (row): row is Record<string, unknown> =>
        Boolean(row) && typeof row === "object" && !Array.isArray(row),
    );
  }
  if (typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    if (Array.isArray(obj.concepts)) {
      return obj.concepts.filter(
        (row): row is Record<string, unknown> =>
          Boolean(row) && typeof row === "object" && !Array.isArray(row),
      );
    }
    if (obj.concept_id) return [obj];
  }
  return [];
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

/** Extract concept surfaces from a parsed business_ontology request payload. */
export function extractBoConcepts(payload: unknown): BoConceptSurface[] {
  const rows = asConceptRows(payload);
  const out: BoConceptSurface[] = [];
  for (const row of rows) {
    const conceptId = String(row.concept_id ?? "").trim();
    if (!conceptId) continue;
    const preferredLabel = String(
      row.preferred_label ?? conceptId,
    ).trim();
    const surfaces = [
      conceptId,
      preferredLabel,
      ...stringList(row.synonyms),
      ...stringList(row.surface_forms),
    ]
      .map(normalize)
      .filter((surface) => surface.length >= 2);
    out.push({
      conceptId,
      preferredLabel,
      surfaces: [...new Set(surfaces)],
    });
  }
  return out;
}

function haystackMatchesSurface(haystack: string, surface: string): boolean {
  if (!haystack || !surface) return false;
  if (haystack === surface) return true;
  // Prefer whole-token / substring matches for multi-word surfaces.
  if (surface.length >= 3 && haystack.includes(surface)) return true;
  if (haystack.length >= 3 && surface.includes(haystack) && haystack.length >= 4) {
    return true;
  }
  return false;
}

function conceptMatchesHaystacks(
  concept: BoConceptSurface,
  haystacks: string[],
): boolean {
  return concept.surfaces.some((surface) =>
    haystacks.some((hay) => haystackMatchesSurface(hay, surface)),
  );
}

export function coverageAgainstHaystacks(
  concepts: BoConceptSurface[],
  haystacksRaw: string[],
): OntologyCoverage {
  const haystacks = [
    ...new Set(
      haystacksRaw
        .map(normalize)
        .filter((value) => value.length >= 2),
    ),
  ];
  if (concepts.length === 0) {
    return {
      total: 0,
      matched: 0,
      ratio: 0,
      matchedConcepts: [],
      missingConcepts: [],
    };
  }
  const matchedConcepts: BoConceptSurface[] = [];
  const missingConcepts: BoConceptSurface[] = [];
  for (const concept of concepts) {
    if (conceptMatchesHaystacks(concept, haystacks)) {
      matchedConcepts.push(concept);
    } else {
      missingConcepts.push(concept);
    }
  }
  return {
    total: concepts.length,
    matched: matchedConcepts.length,
    ratio: matchedConcepts.length / concepts.length,
    matchedConcepts,
    missingConcepts,
  };
}

/** Labels from fused ontology entities, keywords, and optional JSON-LD text. */
export function fusedOntologyHaystacks(
  ontology: FusedOntology | null | undefined,
): string[] {
  if (!ontology) return [];
  const labels = [
    ...ontology.entities.map((entity) => entity.label),
    ...ontology.keywords.map((keyword) => keyword.label),
  ];
  if (ontology.json_ld?.trim()) {
    // Cheap text scan of JSON-LD for preferred labels / IRIs local names.
    labels.push(ontology.json_ld);
  }
  return labels;
}

/** Surfaces for one retrieved chunk (text + linked fused entities/keywords). */
export function chunkOntologyHaystacks(
  chunk: SearchChunkHit,
  ontology: FusedOntology | null | undefined,
): string[] {
  const labels = [chunk.text_raw, chunk.title ?? "", chunk.chunk_id];
  if (ontology) {
    for (const entity of ontology.entities) {
      if (entity.chunk_ids.includes(chunk.chunk_id)) {
        labels.push(entity.label, entity.type);
      }
    }
    for (const keyword of ontology.keywords) {
      if (keyword.chunk_ids.includes(chunk.chunk_id)) {
        labels.push(keyword.label);
      }
    }
  }
  return labels;
}

export function formatCoveragePct(ratio: number): string {
  if (!Number.isFinite(ratio) || ratio <= 0) return "0%";
  return `${Math.round(ratio * 100)}%`;
}
