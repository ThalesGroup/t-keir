"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { MapPin } from "lucide-react";

import {
  labelsToGeocode,
  pinsFromCandidates,
  type LocationCandidate,
  type MapPin as PlacePin,
} from "@/lib/document-locations";
import { geocodePlaceLabels } from "@/lib/geocode-client";
import { cn } from "@/lib/utils";

const MapCanvas = dynamic(
  () =>
    import("@/components/document-places-map-inner").then(
      (mod) => mod.DocumentPlacesMapInner,
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-56 items-center justify-center text-xs text-muted-foreground">
        Loading map…
      </div>
    ),
  },
);

interface DocumentPlacesMapProps {
  candidates: LocationCandidate[];
  title?: string;
  className?: string;
  onSelectChunkIds?: (chunkIds: string[]) => void;
}

export function DocumentPlacesMap({
  candidates,
  title = "Document locations",
  className,
  onSelectChunkIds,
}: DocumentPlacesMapProps) {
  const [geocoded, setGeocoded] = useState<
    Record<string, { lat: number; lon: number; displayName?: string }>
  >({});
  const [busy, setBusy] = useState(false);

  const queries = labelsToGeocode(candidates);
  const queryKey = queries.join("\u0001");

  useEffect(() => {
    const labels = queryKey ? queryKey.split("\u0001") : [];
    if (labels.length === 0) {
      setGeocoded({});
      setBusy(false);
      return;
    }
    let cancelled = false;
    setBusy(true);
    void geocodePlaceLabels(labels).then((results) => {
      if (!cancelled) {
        setGeocoded(results);
        setBusy(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [queryKey]);

  const pins: PlacePin[] = useMemo(
    () => pinsFromCandidates(candidates, geocoded),
    [candidates, geocoded],
  );

  if (candidates.length === 0) return null;

  return (
    <div className={cn("overflow-hidden rounded-md border", className)}>
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground">
        <MapPin className="h-3.5 w-3.5 text-primary" />
        <span>{title}</span>
        {pins.length > 0 && (
          <span className="tabular-nums">
            {pins.length} pin{pins.length === 1 ? "" : "s"}
          </span>
        )}
        {busy && pins.length === 0 && <span>Locating places…</span>}
      </div>
      {pins.length > 0 ? (
        <div className="h-56 w-full">
          <MapCanvas pins={pins} onSelectChunkIds={onSelectChunkIds} />
        </div>
      ) : (
        <p className="px-3 py-4 text-xs text-muted-foreground">
          {busy
            ? "Looking up coordinates for places mentioned in this document."
            : "Places were mentioned, but coordinates could not be resolved."}
        </p>
      )}
    </div>
  );
}
