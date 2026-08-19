import { describe, expect, it } from "vitest";
import { colorForCluster, dbscan, type ClusterableInput } from "./cluster";

// eps defaults to 500km and 1 degree of latitude is ~111km, so ~4.5 degrees of latitude
// is the neighbourhood radius. Fixtures below are spaced in whole degrees to stay well
// clear of that boundary in either direction.
const point = (id: string, lat: number, lng: number): ClusterableInput => ({ id, lat, lng });

function clustersOf(assignment: Map<string, number>): number[] {
  return [...new Set([...assignment.values()].filter((id) => id !== -1))];
}

describe("dbscan", () => {
  it("returns nothing for no points", () => {
    expect(dbscan([]).size).toBe(0);
  });

  it("assigns every input point, so no point renders without a color", () => {
    const points = [point("a", 0, 0), point("b", 1, 0), point("c", 2, 0), point("far", 60, 120)];

    const assignment = dbscan(points);

    expect([...assignment.keys()].sort()).toEqual(["a", "b", "c", "far"]);
    expect([...assignment.values()].every((v) => Number.isInteger(v))).toBe(true);
  });

  it("groups points inside eps into one cluster", () => {
    const assignment = dbscan([point("a", 0, 0), point("b", 1, 0), point("c", 2, 0)]);

    expect(clustersOf(assignment)).toHaveLength(1);
    expect(assignment.get("a")).toBe(assignment.get("b"));
    expect(assignment.get("b")).toBe(assignment.get("c"));
  });

  it("keeps well-separated groups in separate clusters", () => {
    const assignment = dbscan([
      point("a1", 0, 0),
      point("a2", 1, 0),
      point("a3", 2, 0),
      point("b1", 40, 0),
      point("b2", 41, 0),
      point("b3", 42, 0),
    ]);

    expect(clustersOf(assignment)).toHaveLength(2);
    expect(assignment.get("a1")).toBe(assignment.get("a3"));
    expect(assignment.get("b1")).toBe(assignment.get("b3"));
    expect(assignment.get("a1")).not.toBe(assignment.get("b1"));
  });

  it("marks an isolated point as noise rather than giving it its own cluster", () => {
    const assignment = dbscan([point("a", 0, 0), point("b", 1, 0), point("c", 2, 0), point("lonely", -60, 150)]);

    expect(assignment.get("lonely")).toBe(-1);
    expect(clustersOf(assignment)).toHaveLength(1);
  });

  it("marks everything as noise when no neighbourhood reaches minPts", () => {
    const assignment = dbscan([point("a", 0, 0), point("b", 30, 0), point("c", 60, 0)]);

    expect([...assignment.values()]).toEqual([-1, -1, -1]);
  });

  it("treats minPts as inclusive of the point itself", () => {
    const twoTogether = dbscan([point("a", 0, 0), point("b", 1, 0)], 500, 3);
    const threeTogether = dbscan([point("a", 0, 0), point("b", 1, 0), point("c", 2, 0)], 500, 3);

    expect(clustersOf(twoTogether)).toHaveLength(0);
    expect(clustersOf(threeTogether)).toHaveLength(1);
  });

  it("chains transitively through density-reachable points", () => {
    // a-b-c-d each ~333km apart: a and d are ~1000km apart, well beyond eps, but the
    // chain is unbroken so DBSCAN must still put them in one cluster.
    const assignment = dbscan([point("a", 0, 0), point("b", 3, 0), point("c", 6, 0), point("d", 9, 0)]);

    expect(clustersOf(assignment)).toHaveLength(1);
    expect(assignment.get("a")).toBe(assignment.get("d"));
  });

  it("respects a custom eps", () => {
    const points = [point("a", 0, 0), point("b", 3, 0), point("c", 6, 0)];

    expect(clustersOf(dbscan(points, 500, 3))).toHaveLength(1);
    expect(clustersOf(dbscan(points, 100, 3))).toHaveLength(0); // 333km apart, now too far
  });

  it("narrows longitude distance with latitude, so high-latitude points cluster", () => {
    // 10 degrees of longitude is ~1110km at the equator but only ~190km at 80N. The
    // cos(lat) factor in distanceKm is what makes the second group cluster and the
    // first not - a naive flat degree distance would treat them identically.
    const atEquator = [point("a", 0, 0), point("b", 0, 10), point("c", 0, 20)];
    const nearPole = [point("a", 80, 0), point("b", 80, 10), point("c", 80, 20)];

    expect(clustersOf(dbscan(atEquator))).toHaveLength(0);
    expect(clustersOf(dbscan(nearPole))).toHaveLength(1);
  });

  it("puts coincident points in the same cluster", () => {
    // Country-centroid geo (see ingestion/common/geo.py) gives every IOC from one
    // country identical coordinates, so exact duplicates are the common case here.
    const assignment = dbscan([point("a", 37.09, -95.71), point("b", 37.09, -95.71), point("c", 37.09, -95.71)]);

    expect(clustersOf(assignment)).toHaveLength(1);
  });

  it("numbers clusters from zero with no gaps, so palette cycling stays even", () => {
    const assignment = dbscan([
      point("a1", 0, 0),
      point("a2", 1, 0),
      point("a3", 2, 0),
      point("b1", 40, 0),
      point("b2", 41, 0),
      point("b3", 42, 0),
      point("noise", -70, 170),
    ]);

    expect(clustersOf(assignment).sort()).toEqual([0, 1]);
  });
});

describe("colorForCluster", () => {
  it("gives noise its own de-emphasised color", () => {
    expect(colorForCluster(-1)).toBe("#71717a");
  });

  it("gives adjacent clusters distinct colors", () => {
    expect(colorForCluster(0)).not.toBe(colorForCluster(1));
  });

  it("cycles the palette rather than running out of colors", () => {
    expect(colorForCluster(10)).toBe(colorForCluster(0));
    expect(colorForCluster(21)).toBe(colorForCluster(1));
  });

  it("never returns the noise color for a real cluster", () => {
    for (let i = 0; i < 25; i++) {
      expect(colorForCluster(i)).not.toBe(colorForCluster(-1));
    }
  });
});
