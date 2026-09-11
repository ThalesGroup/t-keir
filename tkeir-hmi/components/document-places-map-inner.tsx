"use client";

import { useEffect } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";

import type { MapPin } from "@/lib/document-locations";

import "leaflet/dist/leaflet.css";

function pinIcon() {
  return L.divIcon({
    className: "tkeir-map-pin",
    html: "<span class=\"tkeir-map-pin-dot\"></span>",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    popupAnchor: [0, -10],
  });
}

function FitPins({ pins }: { pins: MapPin[] }) {
  const map = useMap();
  useEffect(() => {
    if (pins.length === 0) return;
    if (pins.length === 1) {
      map.setView([pins[0].lat, pins[0].lon], 5);
      return;
    }
    const bounds = L.latLngBounds(pins.map((pin) => [pin.lat, pin.lon]));
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 7 });
  }, [map, pins]);
  return null;
}

export function DocumentPlacesMapInner({
  pins,
  onSelectChunkIds,
}: {
  pins: MapPin[];
  onSelectChunkIds?: (chunkIds: string[]) => void;
}) {
  if (pins.length === 0) return null;
  const icon = pinIcon();

  return (
    <MapContainer
      center={[pins[0].lat, pins[0].lon]}
      zoom={4}
      scrollWheelZoom
      className="h-full w-full rounded-md"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitPins pins={pins} />
      {pins.map((pin) => (
        <Marker
          key={pin.id}
          position={[pin.lat, pin.lon]}
          icon={icon}
          eventHandlers={
            onSelectChunkIds
              ? {
                  click: () => onSelectChunkIds(pin.chunkIds),
                }
              : undefined
          }
        >
          <Popup>
            <div className="text-xs">
              <p className="font-medium">{pin.label}</p>
              {pin.displayName && pin.displayName !== pin.label ? (
                <p className="text-muted-foreground">{pin.displayName}</p>
              ) : null}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
