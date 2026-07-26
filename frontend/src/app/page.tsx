"use client";

import { useState } from "react";
import ThreatGlobe from "@/components/ThreatGlobe";
import ThreatMap2D from "@/components/ThreatMap2D";
import type { IOCPoint } from "@/lib/types";

// Placeholder data until the backend API (backend/api/handler.py) is deployed and
// wired up in Phase 1 — replace with a real fetch("/api/iocs") once that exists.
const PLACEHOLDER_POINTS: IOCPoint[] = [
  { id: "1", lat: 52.52, lng: 13.405, label: "Placeholder IOC — Berlin" },
  { id: "2", lat: 37.7749, lng: -122.4194, label: "Placeholder IOC — San Francisco" },
  { id: "3", lat: 1.3521, lng: 103.8198, label: "Placeholder IOC — Singapore" },
];

export default function Home() {
  const [view, setView] = useState<"globe" | "2d">("globe");

  return (
    <div className="flex h-screen w-screen flex-col bg-black text-zinc-50">
      <header className="flex items-center justify-between px-6 py-4">
        <h1 className="text-xl font-semibold">Cyvora</h1>
        <div className="flex gap-2 text-sm">
          <button
            onClick={() => setView("globe")}
            className={`rounded-full px-4 py-1.5 ${view === "globe" ? "bg-white text-black" : "bg-zinc-800"}`}
          >
            Globe
          </button>
          <button
            onClick={() => setView("2d")}
            className={`rounded-full px-4 py-1.5 ${view === "2d" ? "bg-white text-black" : "bg-zinc-800"}`}
          >
            2D map
          </button>
        </div>
      </header>
      <main className="flex-1">
        {view === "globe" ? (
          <ThreatGlobe points={PLACEHOLDER_POINTS} />
        ) : (
          <ThreatMap2D points={PLACEHOLDER_POINTS} />
        )}
      </main>
    </div>
  );
}
