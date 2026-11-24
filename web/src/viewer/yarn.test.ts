import { describe, expect, it } from "vitest";
import { buildTube, decodeYarnBin, pointIndices, pointRangeForRows, ringSize, vertexColors, yarnFrames } from "./yarn";

function encode(points: number[][], ids: number[]): ArrayBuffer {
  const n = points.length;
  const buf = new ArrayBuffer(20 + n * 12 + n * 4 + n * 4 + 4);
  const view = new DataView(buf);
  new Uint8Array(buf, 0, 4).set([83, 67, 89, 78]); // "SCYN"
  view.setUint32(4, 1, true);
  view.setUint32(8, n, true);
  view.setUint32(12, 1, true);
  let off = 20;
  for (const p of points) for (const v of p) (view.setFloat32(off, v, true), (off += 4));
  for (let i = 0; i < n; i++) (view.setFloat32(off, 0.5, true), (off += 4));
  for (const id of ids) (view.setUint32(off, id, true), (off += 4));
  view.setUint32(off, 0, true);
  return buf;
}

describe("yarn.bin", () => {
  it("decodes points, radii and stitch ids", () => {
    const yarn = decodeYarnBin(encode([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [3, 3, 4]));
    expect(yarn.count).toBe(3);
    expect(Array.from(yarn.points.slice(3, 6))).toEqual([1, 0, 0]);
    expect(Array.from(yarn.stitchIds)).toEqual([3, 3, 4]);
    expect(yarn.radius[0]).toBeCloseTo(0.5);
  });

  it("rejects other files", () => {
    expect(() => decodeYarnBin(new ArrayBuffer(24))).toThrow();
  });
});

describe("tube geometry", () => {
  const yarn = decodeYarnBin(encode([[0, 0, 0], [1, 0, 0], [2, 0.5, 0], [3, 1, 0]], [1, 1, 2, 2]));

  it("builds one ring of vertices per point with a stitch attribute", () => {
    const g = buildTube(yarn, 6);
    expect(g.getAttribute("position").count).toBe(4 * 7);
    expect(g.getAttribute("stitch").count).toBe(4 * 7);
    expect(g.index!.count).toBe(3 * 6 * 2 * 3);
  });

  it("closes each ring with a seam vertex at u = 1, so the texture does not run backwards over the last face", () => {
    const g = buildTube(yarn, 6);
    const pos = g.getAttribute("position"), uv = g.getAttribute("uv");
    expect(ringSize(6)).toBe(7);
    expect(uv.getX(0)).toBe(0);
    expect(uv.getX(6)).toBe(1);
    for (const axis of ["getX", "getY", "getZ"] as const) expect(pos[axis](6)).toBeCloseTo(pos[axis](0), 6);
  });

  it("builds a tube through a subset of the points, e.g. every second one for the far level", () => {
    const g = buildTube(yarn, 4, pointIndices(0, 3, 2));
    expect(g.getAttribute("position").count).toBe(3 * 5);
    expect(g.getAttribute("stitch").getX(2 * 5)).toBe(2); // third ring: point 3
  });

  it("gives chunks of the same yarn identical rings at shared points, with v shifted by whole tiles", () => {
    const long = decodeYarnBin(encode(Array.from({ length: 40 }, (_, i) => [i, Math.sin(i / 3), Math.cos(i / 5)]), Array(40).fill(1)));
    const frames = yarnFrames(long);
    const full = buildTube(long, 8, pointIndices(0, 39), frames);
    const tail = buildTube(long, 8, pointIndices(20, 39), frames);
    const ring = ringSize(8);
    for (let k = 0; k < ring; k++) {
      const a = 20 * ring + k;
      for (const axis of ["getX", "getY", "getZ"] as const)
        expect(tail.getAttribute("position")[axis](k)).toBeCloseTo(full.getAttribute("position")[axis](a), 5);
      const dv = full.getAttribute("uv").getY(a) - tail.getAttribute("uv").getY(k);
      expect(dv).toBeCloseTo(Math.round(dv), 4);
    }
    expect(tail.getAttribute("uv").getY(0)).toBeLessThan(1);
  });

  it("keeps the ring radius equal to the yarn radius", () => {
    const g = buildTube(yarn, 8);
    const pos = g.getAttribute("position");
    const d = Math.hypot(pos.getX(0) - 0, pos.getY(0) - 0, pos.getZ(0) - 0);
    expect(d).toBeCloseTo(0.5, 5);
  });

  it("maps a row range to an index range for the row slider", () => {
    const rowOf = new Map([[1, 1], [2, 2]]);
    expect(pointRangeForRows(yarn, rowOf, 1)).toBe(2);
    expect(pointRangeForRows(yarn, rowOf, 2)).toBe(4);
  });
});

describe("vertexColors", () => {
  const yarn = decodeYarnBin(encode([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [3, 3, 4]));
  const colorOf = new Map([[3, "#ff0000"], [4, "#0000ff"]]);

  it("colours every ring of the tube like the stitch its point belongs to", () => {
    const c = vertexColors(yarn, 2, colorOf, null, "#00ff00");
    expect(c.length).toBe(3 * 3 * 3);
    expect(Array.from(c.slice(0, 3))).toEqual([1, 0, 0]);
    expect(Array.from(c.slice(24, 27))).toEqual([0, 0, 1]);
  });

  it("paints the selected stitch in the highlight colour", () => {
    const c = vertexColors(yarn, 2, colorOf, 4, "#00ff00");
    expect(Array.from(c.slice(0, 3))).toEqual([1, 0, 0]);
    expect(Array.from(c.slice(18, 27))).toEqual([0, 1, 0, 0, 1, 0, 0, 1, 0]);
  });

  it("colours only the given points", () => {
    const c = vertexColors(yarn, 2, colorOf, null, "#00ff00", pointIndices(1, 2));
    expect(c.length).toBe(2 * 3 * 3);
    expect(Array.from(c.slice(9, 12))).toEqual([0, 0, 1]);
  });
});

describe("pointIndices", () => {
  it("steps through a range and always keeps its last point", () => {
    expect(Array.from(pointIndices(0, 10, 3))).toEqual([0, 3, 6, 9, 10]);
    expect(Array.from(pointIndices(4, 8, 2))).toEqual([4, 6, 8]);
    expect(Array.from(pointIndices(5, 5))).toEqual([5]);
  });
});
