import { NextRequest, NextResponse } from "next/server";

import { MAX_GEOCODE_QUERIES } from "@/lib/document-locations";

type GeoHit = { lat: number; lon: number; displayName: string };

const cache = new Map<string, GeoHit | null>();
const USER_AGENT = "T-KEIR-HMI/2.0 (document place map)";

function cacheKey(query: string): string {
  return query.trim().toLowerCase();
}

async function geocodeOpenMeteo(query: string): Promise<GeoHit | null> {
  const url = new URL("https://geocoding-api.open-meteo.com/v1/search");
  url.searchParams.set("name", query);
  url.searchParams.set("count", "1");
  url.searchParams.set("language", "en");
  url.searchParams.set("format", "json");
  const response = await fetch(url, {
    headers: { Accept: "application/json", "User-Agent": USER_AGENT },
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as {
    results?: Array<{
      latitude?: number;
      longitude?: number;
      name?: string;
      country?: string;
    }>;
  };
  const hit = payload.results?.[0];
  if (hit?.latitude == null || hit?.longitude == null) return null;
  const name = [hit.name, hit.country].filter(Boolean).join(", ");
  return { lat: hit.latitude, lon: hit.longitude, displayName: name || query };
}

async function geocodeNominatim(query: string): Promise<GeoHit | null> {
  const url = new URL("https://nominatim.openstreetmap.org/search");
  url.searchParams.set("q", query);
  url.searchParams.set("format", "jsonv2");
  url.searchParams.set("limit", "1");
  const response = await fetch(url, {
    headers: {
      Accept: "application/json",
      "User-Agent": USER_AGENT,
      "Accept-Language": "en",
    },
  });
  if (!response.ok) return null;
  const payload = (await response.json()) as Array<{
    lat?: string;
    lon?: string;
    display_name?: string;
  }>;
  const hit = payload[0];
  if (!hit?.lat || !hit?.lon) return null;
  return {
    lat: Number(hit.lat),
    lon: Number(hit.lon),
    displayName: hit.display_name || query,
  };
}

async function geocodeOne(query: string): Promise<GeoHit | null> {
  const key = cacheKey(query);
  if (cache.has(key)) return cache.get(key) ?? null;
  let hit: GeoHit | null = null;
  try {
    hit = await geocodeOpenMeteo(query);
  } catch {
    hit = null;
  }
  if (!hit) {
    try {
      hit = await geocodeNominatim(query);
    } catch {
      hit = null;
    }
  }
  cache.set(key, hit);
  return hit;
}

export async function POST(request: NextRequest) {
  let body: { queries?: unknown };
  try {
    body = (await request.json()) as { queries?: unknown };
  } catch {
    return NextResponse.json({ detail: "Invalid JSON" }, { status: 400 });
  }
  const raw = Array.isArray(body.queries) ? body.queries : [];
  const queries = [
    ...new Set(
      raw
        .map((item) => String(item || "").trim())
        .filter((item) => item.length >= 2 && item.length <= 80),
    ),
  ].slice(0, MAX_GEOCODE_QUERIES);

  const results: Record<string, GeoHit> = {};
  await Promise.all(
    queries.map(async (query) => {
      const hit = await geocodeOne(query);
      if (hit) {
        results[query] = hit;
        results[query.toLowerCase()] = hit;
      }
    }),
  );

  return NextResponse.json({ results });
}
