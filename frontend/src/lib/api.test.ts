import { describe, expect, it } from "vitest";
import { rawIocsToPoints } from "./api";
import type { RawIOC } from "./types";

const raw = (over: Partial<RawIOC> = {}): RawIOC => ({
  ioc_id: "abc123",
  ioc_type: "ip",
  value: "45.132.192.10",
  source_feed: "urlhaus",
  tags: [],
  ...over,
});

describe("rawIocsToPoints", () => {
  it("drops IOCs with no geo instead of plotting them at 0,0", () => {
    // Enrichment lags ingestion badly (see fetchIocPoints' comment), so ungeocoded
    // IOCs are normal, not exceptional. Defaulting them would pile the whole backlog
    // onto Null Island.
    const points = rawIocsToPoints([raw(), raw({ ioc_id: "def456", geo: { country: "US", lat: 37.09, lon: -95.71 } })]);

    expect(points).toHaveLength(1);
    expect(points[0].id).toBe("def456");
  });

  it("renames the API's lon to the lng the map components expect", () => {
    const [p] = rawIocsToPoints([raw({ geo: { country: "DE", lat: 51.17, lon: 10.45 } })]);

    expect(p.lat).toBe(51.17);
    expect(p.lng).toBe(10.45);
  });

  it("labels a point with its type and value", () => {
    const [p] = rawIocsToPoints([raw({ geo: { country: "DE", lat: 51.17, lon: 10.45 } })]);

    expect(p.label).toBe("ip: 45.132.192.10");
  });

  it("keeps points on the prime meridian and the equator", () => {
    // A zero lat or lon is a real location, and a truthiness check would drop it.
    const points = rawIocsToPoints([raw({ geo: { country: "GH", lat: 0, lon: 0 } })]);

    expect(points).toHaveLength(1);
    expect(points[0]).toMatchObject({ lat: 0, lng: 0 });
  });

  it("returns nothing for an empty response", () => {
    expect(rawIocsToPoints([])).toEqual([]);
  });
});
