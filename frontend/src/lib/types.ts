// Mirrors the shape of ingestion/common/schema.py's IOC.to_dynamo_item(), flattened
// for the map/globe views (lat/lng pulled out of `geo` once enrichment sets it).
export interface IOCPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
}

// Raw shape returned by GET /iocs (see backend/api/handler.py) - a superset of
// IOCPoint. Not every IOC has `geo` set yet (see ingestion/common/geo.py's coverage
// and EXECUTION_GUIDE.md's notes on this), so IOCPoint conversion filters those out.
export interface RawIOC {
  ioc_id: string;
  ioc_type: string;
  value: string;
  source_feed: string;
  tags: string[];
  confidence?: number;
  geo?: { country: string; lat: number; lon: number };
}
