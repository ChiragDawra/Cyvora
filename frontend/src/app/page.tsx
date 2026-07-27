"use client";

import { useEffect, useState } from "react";
import ThreatGlobe from "@/components/ThreatGlobe";
import ThreatMap2D from "@/components/ThreatMap2D";
import { apiConfigured, fetchIocPoints } from "@/lib/api";
import type { IOCPoint } from "@/lib/types";

const PLACEHOLDER_POINTS: IOCPoint[] = [
  { id: "1", lat: 52.52, lng: 13.405, label: "Placeholder IOC — Berlin" },
  { id: "2", lat: 37.7749, lng: -122.4194, label: "Placeholder IOC — San Francisco" },
  { id: "3", lat: 1.3521, lng: 103.8198, label: "Placeholder IOC — Singapore" },
];

export default function Home() {
  const [view, setView] = useState<"globe" | "2d">("globe");
  const [points, setPoints] = useState<IOCPoint[]>([]);
  const [usingPlaceholder, setUsingPlaceholder] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!apiConfigured()) {
      setPoints(PLACEHOLDER_POINTS);
      setUsingPlaceholder(true);
      setLoading(false);
      return;
    }
    fetchIocPoints()
      .then((fetched) => {
        setPoints(fetched); // real data, even if empty - an empty map is a true state, not an error
        setUsingPlaceholder(false);
      })
      .catch(() => {
        setPoints(PLACEHOLDER_POINTS);
        setUsingPlaceholder(true);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="flex h-screen w-screen flex-col bg-black text-zinc-50">
      <header className="flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-semibold">Cyvora</h1>
          {usingPlaceholder && (
            <span className="rounded-full bg-amber-500/20 px-3 py-1 text-xs text-amber-300">
              Placeholder data — API not configured or unreachable
            </span>
          )}
        </div>
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
        {loading ? null : view === "globe" ? (
          <ThreatGlobe points={points} />
        ) : (
          <ThreatMap2D points={points} />
        )}
      </main>
    </div>
  );
}
