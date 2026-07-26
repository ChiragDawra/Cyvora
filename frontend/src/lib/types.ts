// Mirrors the shape of ingestion/common/schema.py's IOC.to_dynamo_item(), flattened
// for the map/globe views (lat/lng pulled out of `geo` once enrichment sets it).
export interface IOCPoint {
  id: string;
  lat: number;
  lng: number;
  label: string;
}
