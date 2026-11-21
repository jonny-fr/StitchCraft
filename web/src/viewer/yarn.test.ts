import { describe, expect, it } from "vitest";
import { buildTube, decodeYarnBin, pointRangeForRows } from "./yarn";

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
    expect(g.getAttribute("position").count).toBe(4 * 6);
    expect(g.getAttribute("stitch").count).toBe(4 * 6);
    expect(g.index!.count).toBe(3 * 6 * 2 * 3);
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
