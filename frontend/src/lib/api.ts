import type { IOCPoint, RawIOC } from "./types";

// Baked in at build time (static export - see next.config.ts's output: "export").
// Set from the api_url Terraform output after `terraform apply` in infra/, e.g.:
//   NEXT_PUBLIC_API_URL=https://xxxx.execute-api.us-east-1.amazonaws.com npm run build
const API_URL = process.env.NEXT_PUBLIC_API_URL;

export function apiConfigured(): boolean {
  return Boolean(API_URL);
}

export async function fetchIocPoints(): Promise<IOCPoint[]> {
  if (!API_URL) {
    throw new Error("NEXT_PUBLIC_API_URL is not set");
  }
  // Only "ip" IOCs ever get geo (see ingestion/abuseipdb_enrich), and enrichment always
  // lags behind ingestion volume - a plain, recency-sorted /iocs call would return newest
  // IOCs that essentially never have geo yet. ?geo=true asks the API to page backward
  // through the GSI until it finds enough geo-tagged points instead.
  const res = await fetch(`${API_URL}/iocs?type=ip&geo=true`);
  if (!res.ok) {
    throw new Error(`API returned ${res.status}`);
  }
  const body: { items: RawIOC[] } = await res.json();
  return rawIocsToPoints(body.items);
}

// Only IOCs with geo set can be plotted - see ingestion/common/geo.py's coverage and
// EXECUTION_GUIDE.md for why most CVE/URL-type IOCs won't have it yet.
export function rawIocsToPoints(items: RawIOC[]): IOCPoint[] {
  return items
    .filter((item): item is RawIOC & { geo: NonNullable<RawIOC["geo"]> } => item.geo != null)
    .map((item) => ({
      id: item.ioc_id,
      lat: item.geo.lat,
      lng: item.geo.lon,
      label: `${item.ioc_type}: ${item.value}`,
    }));
}
