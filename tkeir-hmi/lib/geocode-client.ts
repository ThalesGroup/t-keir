import type { GeoPoint } from "@/lib/document-locations";

export async function geocodePlaceLabels(
  labels: string[],
): Promise<Record<string, GeoPoint>> {
  const queries = [
    ...new Set(
      labels.map((label) => label.trim()).filter(Boolean),
    ),
  ];
  if (queries.length === 0) return {};
  const response = await fetch("/api/geocode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ queries }),
  });
  if (!response.ok) return {};
  const payload = (await response.json()) as {
    results?: Record<string, GeoPoint>;
  };
  return payload.results ?? {};
}
