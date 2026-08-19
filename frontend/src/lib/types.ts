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

// Row shape returned by GET /alerts (see backend/api/handler.py and
// ingestion/anomaly_detector/handler.py, which writes these).
export interface Alert {
  alert_id: string;
  ioc_type: string;
  date: string;
  count: number;
  baseline_mean: number;
  baseline_stdev: number;
  z_score: number;
  created_at: number;
}
