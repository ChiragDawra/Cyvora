"use client";

// Only ever loaded via next/dynamic({ ssr: false }) from ThreatMap2D.tsx — react-leaflet
// touches `window` at import time, so this file must never be imported at module scope
// from anything that could be server-rendered.
import "leaflet/dist/leaflet.css";
import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import type { IOCPoint } from "@/lib/types";

export default function LeafletMapImpl({ points }: { points: IOCPoint[] }) {
  return (
    <MapContainer center={[20, 0]} zoom={2} style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {points.map((p) => (
        <CircleMarker key={p.id} center={[p.lat, p.lng]} radius={5} pathOptions={{ color: "#ff4d4f" }}>
          <Popup>{p.label}</Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
