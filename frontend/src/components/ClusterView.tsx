"use client";

import { useMemo } from "react";
import ThreatMap2D from "./ThreatMap2D";
import { colorForCluster, dbscan } from "@/lib/cluster";
import type { IOCPoint } from "@/lib/types";

// Reuses the 2D map (react-leaflet already handles pan/zoom/popups well) rather than a
// separate viz library - DBSCAN just recolors the same points by cluster membership.
export default function ClusterView({ points }: { points: IOCPoint[] }) {
  const { colors, clusterCount } = useMemo(() => {
    const assignment = dbscan(points);
    const colors = new Map<string, string>();
    const clusterIds = new Set<number>();
    for (const [id, clusterId] of assignment) {
      colors.set(id, colorForCluster(clusterId));
      if (clusterId !== -1) clusterIds.add(clusterId);
    }
    return { colors, clusterCount: clusterIds.size };
  }, [points]);

  return (
    <div className="relative h-full w-full">
      <ThreatMap2D points={points} colors={colors} />
      <div className="absolute bottom-4 left-4 rounded-full bg-zinc-800/90 px-3 py-1.5 text-xs text-zinc-300">
        {clusterCount} cluster{clusterCount === 1 ? "" : "s"} found ({points.length} points)
      </div>
    </div>
  );
}
