// Small self-contained DBSCAN over lat/lng, run client-side on the same geo-tagged IOC
// points the map/globe already fetch (see lib/api.ts's fetchIocPoints) - no new backend
// job, no new infra, no new npm dependency. Distance is a flat-plane approximation
// (great-circle precision isn't needed for clustering nearby threat infrastructure at
// the zoom levels this app renders).

export interface ClusterableInput {
  id: string;
  lat: number;
  lng: number;
}

// -1 is the DBSCAN convention for "noise" (a point with no cluster).
export type ClusterAssignment = Map<string, number>;

function distanceKm(a: ClusterableInput, b: ClusterableInput): number {
  const dLat = (a.lat - b.lat) * 111; // ~111km per degree latitude everywhere
  const dLng = (a.lng - b.lng) * 111 * Math.cos((((a.lat + b.lat) / 2) * Math.PI) / 180);
  return Math.sqrt(dLat * dLat + dLng * dLng);
}

// eps in km, minPts is the density threshold - both tuned for "malicious infrastructure
// clustered by region", not a general-purpose default.
export function dbscan(points: ClusterableInput[], eps = 500, minPts = 3): ClusterAssignment {
  const assignment: ClusterAssignment = new Map();
  const visited = new Set<string>();
  let nextClusterId = 0;

  const regionQuery = (point: ClusterableInput) =>
    points.filter((p) => distanceKm(point, p) <= eps);

  for (const point of points) {
    if (visited.has(point.id)) continue;
    visited.add(point.id);

    const neighbors = regionQuery(point);
    if (neighbors.length < minPts) {
      assignment.set(point.id, -1); // provisional noise; may be claimed by a later cluster
      continue;
    }

    const clusterId = nextClusterId++;
    assignment.set(point.id, clusterId);

    const queue = [...neighbors];
    while (queue.length > 0) {
      const current = queue.shift()!;
      if (!visited.has(current.id)) {
        visited.add(current.id);
        const currentNeighbors = regionQuery(current);
        if (currentNeighbors.length >= minPts) {
          queue.push(...currentNeighbors);
        }
      }
      if (assignment.get(current.id) === undefined || assignment.get(current.id) === -1) {
        assignment.set(current.id, clusterId);
      }
    }
  }

  return assignment;
}

// Fixed, high-contrast palette cycled by cluster id - readable in both themes, distinct
// from the fixed "#ff4d4f" used for unclustered points elsewhere in the app.
const CLUSTER_COLORS = [
  "#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a78bfa",
  "#4ade80", "#fb923c", "#22d3ee", "#e879f9", "#facc15",
];
const NOISE_COLOR = "#71717a"; // zinc-500 - visually de-emphasized, not alarming red

export function colorForCluster(clusterId: number): string {
  if (clusterId === -1) return NOISE_COLOR;
  return CLUSTER_COLORS[clusterId % CLUSTER_COLORS.length];
}
