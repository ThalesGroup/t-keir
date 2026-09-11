import type { FusedOntology, RetrievedChunk, SemanticEntity } from "@/lib/types";

/** Place mentioned in retrieved documents, optionally with coordinates. */
export interface LocationCandidate {
  label: string;
  type: string;
  chunkIds: string[];
  parentDocIds: string[];
  lat?: number;
  lon?: number;
}

export interface GeoPoint {
  lat: number;
  lon: number;
  displayName?: string;
}

export interface MapPin {
  id: string;
  label: string;
  lat: number;
  lon: number;
  displayName?: string;
  parentDocIds: string[];
  chunkIds: string[];
}

const LOCATION_TYPE_HINTS = [
  "loc",
  "gpe",
  "location",
  "place",
  "city",
  "country",
  "capital",
  "settlement",
  "region",
  "continent",
  "facility",
  "fac",
  "geo",
  "administrative",
  "coast",
  "island",
  "province",
  "state",
  "town",
  "village",
  "harbour",
  "harbor",
  "port",
  "gulf",
  "sea",
  "ocean",
  "river",
  "lake",
  "mountain",
  "desert",
  "territory",
  "nation",
  "land",
];

const GENERIC_LABELS = new Set([
  "place",
  "location",
  "city",
  "country",
  "geography",
  "region",
  "continent",
  "settlement",
  "capital",
  "area",
  "zone",
  "map",
  "maps",
  "localisation",
  "localization",
  "locality",
  "toponym",
  "facility",
  "infrastructure",
  "boundary",
  "cartography",
]);

const LABELED_COORD_RE =
  /(?:lat(?:itude)?)\s*[:=]\s*(-?\d{1,2}(?:\.\d+)?)[,\s;]+(?:lon(?:g(?:itude)?)?)\s*[:=]\s*(-?\d{1,3}(?:\.\d+)?)/gi;

const DMS_COORD_RE =
  /(-?\d{1,2}(?:\.\d+)?)\s*[°º]?\s*([NSns])\s*[,;\s]+\s*(-?\d{1,3}(?:\.\d+)?)\s*[°º]?\s*([EWew])/g;

export function isLocationEntityType(type: string): boolean {
  const normalized = type.trim().toLowerCase();
  if (!normalized) return false;
  return LOCATION_TYPE_HINTS.some(
    (hint) => normalized === hint || normalized.includes(hint),
  );
}

export function isGeocodablePlaceLabel(label: string): boolean {
  const text = label.trim();
  if (text.length < 2 || text.length > 80) return false;
  if (GENERIC_LABELS.has(text.toLowerCase())) return false;
  if (/^[\d\s.,;:+\-_/]+$/.test(text)) return false;
  if (!/[a-zA-Z\u00C0-\u024F\u0400-\u04FF]/.test(text)) return false;
  return true;
}

function validLatLon(lat: number, lon: number): boolean {
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lon) &&
    lat >= -90 &&
    lat <= 90 &&
    lon >= -180 &&
    lon <= 180 &&
    !(lat === 0 && lon === 0)
  );
}

/** Parse explicit latitude/longitude mentions from passage text. */
export function extractCoordinatesFromText(
  text: string,
): Array<{ lat: number; lon: number; label: string }> {
  const found: Array<{ lat: number; lon: number; label: string }> = [];
  const seen = new Set<string>();

  const push = (lat: number, lon: number, label: string) => {
    if (!validLatLon(lat, lon)) return;
    const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
    if (seen.has(key)) return;
    seen.add(key);
    found.push({ lat, lon, label });
  };

  for (const match of text.matchAll(LABELED_COORD_RE)) {
    push(
      Number(match[1]),
      Number(match[2]),
      `${Number(match[1]).toFixed(3)}, ${Number(match[2]).toFixed(3)}`,
    );
  }

  for (const match of text.matchAll(DMS_COORD_RE)) {
    let lat = Number(match[1]);
    let lon = Number(match[3]);
    if (match[2].toUpperCase() === "S") lat = -Math.abs(lat);
    if (match[2].toUpperCase() === "N") lat = Math.abs(lat);
    if (match[4].toUpperCase() === "W") lon = -Math.abs(lon);
    if (match[4].toUpperCase() === "E") lon = Math.abs(lon);
    push(
      lat,
      lon,
      `${Math.abs(Number(match[1]))}°${match[2].toUpperCase()} ${Math.abs(Number(match[3]))}°${match[4].toUpperCase()}`,
    );
  }

  return found;
}

function parentDocIdForChunk(
  chunkId: string,
  chunks: Array<{ chunk_id: string; parent_doc_id: string }>,
): string | null {
  const hit = chunks.find((chunk) => chunk.chunk_id === chunkId);
  return hit?.parent_doc_id ?? null;
}

function addCandidate(
  byKey: Map<string, LocationCandidate>,
  candidate: LocationCandidate,
) {
  const key =
    candidate.lat != null && candidate.lon != null
      ? `coord:${candidate.lat.toFixed(4)},${candidate.lon.toFixed(4)}`
      : `name:${candidate.label.trim().toLowerCase()}`;
  const existing = byKey.get(key);
  if (!existing) {
    byKey.set(key, {
      ...candidate,
      chunkIds: [...new Set(candidate.chunkIds)],
      parentDocIds: [...new Set(candidate.parentDocIds.filter(Boolean))],
    });
    return;
  }
  existing.chunkIds = [...new Set([...existing.chunkIds, ...candidate.chunkIds])];
  existing.parentDocIds = [
    ...new Set([...existing.parentDocIds, ...candidate.parentDocIds].filter(Boolean)),
  ];
}

/** Location entities and coordinates evidenced on retrieved chunks. */
export function collectLocationCandidates(
  ontology: FusedOntology | null | undefined,
  chunks: Array<Pick<RetrievedChunk, "chunk_id" | "parent_doc_id" | "text_raw">>,
): LocationCandidate[] {
  const byKey = new Map<string, LocationCandidate>();

  for (const entity of ontology?.entities ?? []) {
    if (!isLocationEntity(entity)) continue;
    const parentDocIds = [
      ...new Set(
        entity.chunk_ids
          .map((chunkId) => parentDocIdForChunk(chunkId, chunks))
          .filter((id): id is string => Boolean(id)),
      ),
    ];
    if (parentDocIds.length === 0 && chunks.length > 0) continue;
    addCandidate(byKey, {
      label: entity.label.trim(),
      type: entity.type,
      chunkIds: [...entity.chunk_ids],
      parentDocIds,
    });
  }

  for (const chunk of chunks) {
    for (const coord of extractCoordinatesFromText(chunk.text_raw || "")) {
      addCandidate(byKey, {
        label: coord.label,
        type: "coordinates",
        chunkIds: [chunk.chunk_id],
        parentDocIds: [chunk.parent_doc_id],
        lat: coord.lat,
        lon: coord.lon,
      });
    }
  }

  return [...byKey.values()].sort(
    (a, b) =>
      b.chunkIds.length - a.chunkIds.length ||
      a.label.localeCompare(b.label),
  );
}

export function isLocationEntity(entity: SemanticEntity): boolean {
  if (!isLocationEntityType(entity.type)) return false;
  return isGeocodablePlaceLabel(entity.label);
}

export function locationsForDocument(
  candidates: LocationCandidate[],
  parentDocId: string,
): LocationCandidate[] {
  return candidates.filter((row) => row.parentDocIds.includes(parentDocId));
}

export const MAX_GEOCODE_QUERIES = 12;

export function labelsToGeocode(candidates: LocationCandidate[]): string[] {
  const labels: string[] = [];
  const seen = new Set<string>();
  for (const row of candidates) {
    if (row.lat != null && row.lon != null) continue;
    const key = row.label.trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    labels.push(row.label.trim());
    if (labels.length >= MAX_GEOCODE_QUERIES) break;
  }
  return labels;
}

export function pinsFromCandidates(
  candidates: LocationCandidate[],
  geocoded: Record<string, GeoPoint>,
): MapPin[] {
  const pins: MapPin[] = [];
  const seen = new Set<string>();
  for (const row of candidates) {
    const point =
      row.lat != null && row.lon != null
        ? { lat: row.lat, lon: row.lon, displayName: row.label }
        : geocoded[row.label.trim()] ??
          geocoded[row.label.trim().toLowerCase()];
    if (!point || !validLatLon(point.lat, point.lon)) continue;
    const id = `${point.lat.toFixed(4)},${point.lon.toFixed(4)}:${row.label}`;
    if (seen.has(id)) continue;
    seen.add(id);
    pins.push({
      id,
      label: row.label,
      lat: point.lat,
      lon: point.lon,
      displayName: point.displayName,
      parentDocIds: row.parentDocIds,
      chunkIds: row.chunkIds,
    });
  }
  return pins;
}
