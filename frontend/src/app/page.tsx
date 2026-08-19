"use client";

import { useEffect, useState } from "react";
import ThreatGlobe from "@/components/ThreatGlobe";
import ThreatMap2D from "@/components/ThreatMap2D";
import ClusterView from "@/components/ClusterView";
import { apiConfigured, fetchAlerts, fetchIocPoints } from "@/lib/api";
import type { Alert, IOCPoint } from "@/lib/types";

const PLACEHOLDER_POINTS: IOCPoint[] = [
  { id: "1", lat: 52.52, lng: 13.405, label: "Placeholder IOC — Berlin" },
  { id: "2", lat: 37.7749, lng: -122.4194, label: "Placeholder IOC — San Francisco" },
  { id: "3", lat: 1.3521, lng: 103.8198, label: "Placeholder IOC — Singapore" },
];

export default function Home() {
  const [view, setView] = useState<"globe" | "2d" | "clusters">("globe");
  // NEXT_PUBLIC_API_URL is baked in at build time (static export), so whether the API is
  // configured is known before the first render - no need to mount empty and then set
  // state from an effect, which only bought an extra render and a lint error.
  const [points, setPoints] = useState<IOCPoint[]>(apiConfigured() ? [] : PLACEHOLDER_POINTS);
  const [usingPlaceholder, setUsingPlaceholder] = useState(!apiConfigured());
  const [loading, setLoading] = useState(apiConfigured());
  const [alerts, setAlerts] = useState<Alert[]>([]);

  useEffect(() => {
    if (!apiConfigured()) return;

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

    fetchAlerts().then(setAlerts); // empty on any failure - see lib/api.ts's fetchAlerts
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
          {alerts.length > 0 && (
            <span className="rounded-full bg-red-500/20 px-3 py-1 text-xs text-red-300">
              {alerts.length} spike alert{alerts.length === 1 ? "" : "s"}
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
          <button
            onClick={() => setView("clusters")}
            className={`rounded-full px-4 py-1.5 ${view === "clusters" ? "bg-white text-black" : "bg-zinc-800"}`}
          >
            Clusters
          </button>
        </div>
      </header>
      <main className="relative flex-1">
        {loading ? null : view === "globe" ? (
          <ThreatGlobe points={points} />
        ) : view === "2d" ? (
          <ThreatMap2D points={points} />
        ) : (
          <ClusterView points={points} />
        )}
        {alerts.length > 0 && (
          <div className="absolute top-4 right-4 max-h-64 w-72 overflow-y-auto rounded-lg bg-zinc-900/90 p-3 text-xs">
            <div className="mb-2 font-semibold text-zinc-300">Recent spike alerts</div>
            {alerts.map((a) => (
              <div key={a.alert_id} className="mb-2 rounded-full bg-red-500/10 px-3 py-1.5 text-red-300">
                {a.ioc_type} — {a.count} on {a.date} (z={a.z_score})
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
